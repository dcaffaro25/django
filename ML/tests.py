from django.test import TestCase
from rest_framework.test import APIClient
from django.urls import reverse
from datetime import date

from multitenancy.models import Company, Entity
from accounting.models import Currency, Account, Transaction, JournalEntry
from .utils.train import train_categorization_model


class CategorizationModelTests(TestCase):
    """
    Teste de integração: constrói três contas distintas e treina o modelo
    com 10 transações por conta, cada uma contendo duas entradas de diário.
    Isso garante exemplos suficientes para cada classe e verifica se o
    endpoint de predição retorna a conta correta.
    """

    def setUp(self):
        # Criação da empresa e da moeda
        self.company = Company.objects.create(name="TestCo", subdomain="testco")
        self.currency = Currency.objects.create(code="USD", name="US Dollar", symbol="$")
        self.entity = Entity.objects.create(company=self.company, name="Main Entity")

        # Criação das contas: caixa, despesa de aluguel e receita de serviços
        self.cash_account = Account.objects.create(
            company=self.company,
            account_code="1.1",
            name="Cash",
            description="Dinheiro em caixa",
            key_words="receita recebimento",
            examples="Recebimento de vendas",
            account_direction=1,
            balance_date=date.today(),
            balance=0,
            currency=self.currency,
            is_active=True,
        )
        self.expense_account = Account.objects.create(
            company=self.company,
            account_code="5.1",
            name="Rent Expense",
            description="Pagamento de aluguel",
            key_words="despesa pagamento",
            examples="Pagamento de aluguel e despesas",
            account_direction=1,
            balance_date=date.today(),
            balance=0,
            currency=self.currency,
            is_active=True,
        )
        self.service_account = Account.objects.create(
            company=self.company,
            account_code="4.1",
            name="Service Revenue",
            description="Venda de serviços",
            key_words="receita serviços",
            examples="Prestação de serviços",
            account_direction=1,
            balance_date=date.today(),
            balance=0,
            currency=self.currency,
            is_active=True,
        )

        # 1) Conta de caixa: "Recebimento de venda" (10 transações, 2 lançamentos por transação)
        for i in range(10):
            tx = Transaction.objects.create(
                company=self.company,
                entity=self.entity,
                date=date.today(),
                description="Recebimento de venda",
                amount=100 + i,
                currency=self.currency,
                state="posted",
            )
            JournalEntry.objects.create(
                company=self.company,
                transaction=tx,
                account=self.cash_account,
                debit_amount=tx.amount,
                state="posted",
            )
            JournalEntry.objects.create(
                company=self.company,
                transaction=tx,
                account=self.cash_account,
                credit_amount=tx.amount,
                state="posted",
            )

        # 2) Conta de despesas: "Pagamento de aluguel"
        for i in range(10):
            tx = Transaction.objects.create(
                company=self.company,
                entity=self.entity,
                date=date.today(),
                description="Pagamento de aluguel",
                amount=50 + i,
                currency=self.currency,
                state="posted",
            )
            JournalEntry.objects.create(
                company=self.company,
                transaction=tx,
                account=self.expense_account,
                debit_amount=tx.amount,
                state="posted",
            )
            JournalEntry.objects.create(
                company=self.company,
                transaction=tx,
                account=self.expense_account,
                credit_amount=tx.amount,
                state="posted",
            )

        # 3) Conta de receitas de serviços: "Venda de serviços"
        for i in range(10):
            tx = Transaction.objects.create(
                company=self.company,
                entity=self.entity,
                date=date.today(),
                description="Venda de serviços",
                amount=200 + i,
                currency=self.currency,
                state="posted",
            )
            JournalEntry.objects.create(
                company=self.company,
                transaction=tx,
                account=self.service_account,
                debit_amount=tx.amount,
                state="posted",
            )
            JournalEntry.objects.create(
                company=self.company,
                transaction=tx,
                account=self.service_account,
                credit_amount=tx.amount,
                state="posted",
            )

        # Treinamento do modelo de categorização
        self.ml_model = train_categorization_model(
            company_id=self.company.id,
            records_per_account=10,
            training_fields=["description", "amount"],
            prediction_fields=["description", "amount"],
        )

    def test_predict_endpoint_with_model_id(self):
        """
        Verifica se a conta de despesa (Rent Expense) é sugerida corretamente
        quando se passa o model_id explicitamente.
        """
        client = APIClient()
        url = reverse("ml-model-predict")
        response = client.post(
            url,
            data={
                "model_id": self.ml_model.id,
                "transaction": {"description": "Pagamento de aluguel", "amount": 50},
                "top_n": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        top_prediction = result["predictions"][0]
        self.assertEqual(top_prediction["account_id"], self.expense_account.id)
        self.assertGreaterEqual(top_prediction["probability"], 0.5)

    def test_predict_endpoint_with_company_id(self):
        """
        Verifica se o endpoint seleciona o modelo mais recente usando company_id
        e sugere a conta de caixa para a descrição 'Recebimento de venda'.
        """
        client = APIClient()
        url = reverse("ml-model-predict")
        response = client.post(
            url,
            data={
                "company_id": self.company.id,
                "transaction": {"description": "Recebimento de venda", "amount": 100},
                "top_n": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        top_prediction = result["predictions"][0]
        self.assertEqual(top_prediction["account_id"], self.cash_account.id)
        self.assertGreaterEqual(top_prediction["probability"], 0.5)

    def test_predict_endpoint_service_account(self):
        """
        Verifica se a descrição 'Venda de serviços' retorna a conta de receita de serviços.
        """
        client = APIClient()
        url = reverse("ml-model-predict")
        response = client.post(
            url,
            data={
                "company_id": self.company.id,
                "transaction": {"description": "Venda de serviços", "amount": 200},
                "top_n": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        top_prediction = result["predictions"][0]
        self.assertEqual(top_prediction["account_id"], self.service_account.id)
        self.assertGreaterEqual(top_prediction["probability"], 0.5)

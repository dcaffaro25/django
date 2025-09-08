from django.test import TestCase
from multitenancy.models import CustomUser, Company, Entity
from django.contrib.auth import get_user_model
# django/multitenancy/tests.py
from django.urls import reverse
from rest_framework.test import APIClient
from multitenancy.models import SubstitutionRule, IntegrationRule

class ImportAndSubstitutionTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="TestCo", subdomain="testco")
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username="testuser", password="secret")
        self.client.force_authenticate(user=self.user)
        # Força autenticação/tenant se necessário

        # Regras de substituição
        SubstitutionRule.objects.create(
            company=self.company,
            model_name="Employee",
            field_name="status",
            match_type="caseless",
            match_value="ativo",
            substitution_value="Ativo"
        )
        SubstitutionRule.objects.create(
            company=self.company,
            column_name="Status",
            match_type="exact",
            match_value="INATIVO",
            substitution_value="Inativo"
        )

    def test_apply_substitution_to_model_field(self):
        from multitenancy.formula_engine import apply_substitutions
        payload = [{"status": "ATIVO", "salary": 1000}]
        result = apply_substitutions(payload, self.company.id, model_name="Employee")
        self.assertEqual(result[0]["status"], "Ativo")

    def test_bulk_import_sync(self):
        import pandas as pd
        from io import BytesIO
        df = pd.DataFrame([{"name": "Ana", "status": "ativo"}])
        buffer = BytesIO()
        df.to_excel(buffer, index=False)
        buffer.seek(0)
        response = self.client.post(
            reverse('bulk-import'),
            {
                "file": buffer,
                "use_celery": False,
                "company_id": self.company.id  # informa a empresa
            },
            format='multipart'
        )
        self.assertEqual(response.status_code, 202)
        # Verifica que houve substituição
        # (dependendo de como safe_model_dict serializa status)

    # Você pode adicionar mais testes de integração aqui


'''
class CustomUserModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Set up non-modified objects used by all test methods
        CustomUser.objects.create(username='testuser', password='foo')

    def test_user_creation(self):
        user = CustomUser.objects.get(id=1)
        self.assertEqual(user.username, 'testuser')

class CompanyModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create a Company object to test with
        Company.objects.create(name='Test Company', subdomain='test-company')

    def test_company_creation(self):
        company = Company.objects.get(id=1)
        self.assertEqual(company.name, 'Test Company')

    def test_subdomain_auto_generation(self):
        # Test the auto-generation of subdomain based on the company name
        company = Company.objects.get(id=1)
        self.assertEqual(company.subdomain, 'test-company')

    def test_subdomain_uniqueness(self):
        # Test that creating a second company with the same subdomain raises an error
        with self.assertRaises(ValueError):
            Company.objects.create(name='Another Test Company', subdomain='test-company')

class EntityModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='Test Company', subdomain='test-company')
        Entity.objects.create(name='Test Entity', company=company)

    def test_entity_creation(self):
        entity = Entity.objects.get(id=1)
        self.assertEqual(entity.name, 'Test Entity')

    def test_get_path(self):
        # Test the get_path method functionality
        company = Company.objects.get(id=1)
        parent_entity = Entity.objects.create(name='Parent Entity', company=company)
        child_entity = Entity.objects.create(name='Child Entity', company=company, parent=parent_entity)
        self.assertEqual(child_entity.get_path(), 'Parent Entity > Child Entity')
'''

# 05 — Contabilidade

O módulo de contabilidade é o coração da plataforma Nord. Ele gerencia o plano de contas, transações, lançamentos contábeis, contas bancárias e centros de custo.

---

## 5.1 Plano de Contas (Accounts)

### Estrutura Hierárquica

O plano de contas é organizado em **árvore** (MPTT), seguindo o padrão contábil brasileiro:

```
1       Ativo
1.1       Ativo Circulante
1.1.1       Caixa e Equivalentes de Caixa
1.1.1.001     Banco do Brasil C/C 12345
1.1.1.002     Caixa Geral
1.1.2       Contas a Receber
1.1.2.001     Clientes Nacionais
1.2       Ativo Não Circulante
2       Passivo
2.1       Passivo Circulante
2.1.1       Fornecedores
3       Patrimônio Líquido
4       Receitas
4.1       Receita Operacional
5       Despesas
5.1       Despesas Administrativas
```

### Campos da Conta

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `account_code` | string | Código hierárquico (ex: `1.1.1.001`) |
| `name` | string | Nome da conta |
| `parent` | FK Account | Conta-pai na árvore |
| `currency` | FK Currency | Moeda da conta |
| `bank_account` | FK BankAccount | Conta bancária vinculada (opcional) |
| `account_direction` | choice | Direção: `debit` ou `credit` |
| `balance` | decimal | Saldo atual |
| `balance_date` | date | Data do saldo |
| `cliente_erp_id` | string | ID no ERP externo |

### Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/{tenant}/api/accounts/` | Listar contas |
| `POST` | `/{tenant}/api/accounts/` | Criar conta |
| `GET` | `/{tenant}/api/accounts/{id}/` | Detalhe |
| `PUT/PATCH` | `/{tenant}/api/accounts/{id}/` | Atualizar |
| `DELETE` | `/{tenant}/api/accounts/{id}/` | Excluir |
| `POST` | `/{tenant}/api/accounts/bulk_create/` | Criar em lote |
| `POST` | `/{tenant}/api/accounts/bulk_update/` | Atualizar em lote |
| `POST` | `/{tenant}/api/accounts/bulk_delete/` | Excluir em lote |

### Exemplo: Criar uma Conta

```bash
POST /acme/api/accounts/
{
  "account_code": "1.1.1.003",
  "name": "Itaú C/C 67890",
  "parent": 3,
  "currency": 1,
  "account_direction": "debit"
}
```

### Exemplo: Importar Plano de Contas em Lote

```bash
POST /acme/api/accounts/bulk_create/
[
  {"account_code": "1", "name": "Ativo", "account_direction": "debit", "currency": 1},
  {"account_code": "1.1", "name": "Ativo Circulante", "parent_code": "1", "currency": 1},
  {"account_code": "2", "name": "Passivo", "account_direction": "credit", "currency": 1}
]
```

> **Dica:** Para importar planos de contas extensos, use o [Pipeline ETL](11-etl-importacao.md) que suporta planilhas Excel e aplica regras de substituição automaticamente.

---

## 5.2 Transações (Transactions)

Transações são os registros financeiros principais. Cada transação pode conter múltiplos lançamentos contábeis (journal entries).

### Campos da Transação

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `entity` | FK Entity | Entidade responsável |
| `date` | date | Data da transação |
| `amount` | decimal | Valor total |
| `currency` | FK Currency | Moeda |
| `description` | text | Descrição |
| `state` | choice | Estado: `draft`, `posted`, `cancelled` |
| `due_date` | date | Data de vencimento do título/obrigação financeira (opcional) |
| `nf_number` | string | Número da Nota Fiscal associada (opcional) |
| `cliente_erp_id` | string | ID no ERP externo para integração |

### Ciclo de Vida

```
                    ┌──────────┐
    Criação ───────►│  DRAFT   │
                    └────┬─────┘
                         │ POST
                    ┌────▼─────┐
                    │  POSTED  │
                    └────┬─────┘
                         │ CANCEL
                    ┌────▼──────┐
                    │ CANCELLED │
                    └───────────┘
```

### Ações Especiais

| Ação | Método | Endpoint | Descrição |
|------|--------|----------|-----------|
| **Postar** | `POST` | `/{tenant}/transactions/{id}/post/` | Confirma a transação |
| **Despostar** | `POST` | `/{tenant}/transactions/{id}/unpost/` | Reverte para rascunho |
| **Cancelar** | `POST` | `/{tenant}/transactions/{id}/cancel/` | Cancela a transação |
| **Balancear** | `POST` | `/{tenant}/transactions/{id}/create_balancing_entry/` | Cria lançamento de ajuste |

### Verificação de Saldo

Toda transação deve ter **débitos = créditos** em seus lançamentos. Endpoints para verificar:

```bash
# Verificar saldo de uma transação
GET /acme/api/transactions/{id}/validate-balance/

# Verificar saldo em lote
POST /acme/api/transactions/bulk-validate-balance/
{"transaction_ids": [1, 2, 3]}

# Listar transações desbalanceadas
GET /acme/api/transactions/unbalanced/
```

### Estatísticas Resumidas

```bash
GET /acme/api/transactions/summary-stats/
```

Retorna contagens por estado, totais e médias.

### Filtros Avançados

```bash
# Transações de março de 2026, postadas, da entidade 5
GET /acme/api/transactions/?date_after=2026-03-01&date_before=2026-03-31&state=posted&entity=5

# Transações não conciliadas
GET /acme/api/transactions/unmatched/

# Busca textual (pesquisa em description, nf_number, cliente_erp_id, numero_boleto, cnpj)
GET /acme/api/transactions/?search=aluguel+sede

# Filtrar por Nota Fiscal
GET /acme/api/transactions/?nf_number=000123456

# Filtrar por ID do ERP externo
GET /acme/api/transactions/?cliente_erp_id=ERP-TX-001

# Filtrar por data de vencimento
GET /acme/api/transactions/?due_date_from=2026-03-01&due_date_to=2026-03-31

# Combinar filtros: NFs vencidas no mês e não conciliadas
GET /acme/api/transactions/unmatched/?due_date_from=2026-03-01&due_date_to=2026-03-31&nf_number=000123
```

---

## 5.3 Lançamentos Contábeis (Journal Entries)

Cada transação contém um ou mais lançamentos contábeis que debitam/creditam contas específicas.

### Campos do Lançamento

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `transaction` | FK Transaction | Transação-pai |
| `account` | FK Account | Conta contábil |
| `cost_center` | FK CostCenter | Centro de custo (opcional) |
| `debit` | decimal | Valor a débito |
| `credit` | decimal | Valor a crédito |
| `state` | choice | Estado (herda da transação) |
| `tag` | string | Tag livre para classificação e agrupamento na conciliação |
| `cliente_erp_id` | string | ID no ERP externo |

> **Campos herdados da Transação-pai:** Na listagem, cada lançamento também exibe `due_date`, `nf_number` e `cliente_erp_id` da transação associada. Isso permite filtrar lançamentos por data de vencimento, NF ou ID ERP sem precisar consultar a transação separadamente.

### Filtros de Lançamentos

```bash
# Lançamentos com tag específica
GET /acme/api/journal_entries/?tag=aluguel

# Lançamentos por NF da transação-pai
GET /acme/api/journal_entries/?transaction_nf_number=000123456

# Lançamentos por data de vencimento da transação
GET /acme/api/journal_entries/?transaction_due_date_from=2026-03-01&transaction_due_date_to=2026-03-31

# Lançamentos por ID ERP do cliente
GET /acme/api/journal_entries/?cliente_erp_id=ERP-JE-001
```

### Exemplo: Lançamento de Pagamento de Aluguel

Uma transação de R$ 5.000 de aluguel geraria dois lançamentos:

```json
[
  {
    "transaction": 100,
    "account": 45,
    "debit": 5000.00,
    "credit": 0,
    "tag": "aluguel"
  },
  {
    "transaction": 100,
    "account": 12,
    "debit": 0,
    "credit": 5000.00,
    "tag": "aluguel"
  }
]
```

> Conta 45 = "Despesas com Aluguel" (débito) / Conta 12 = "Banco C/C" (crédito)

### Sugestão de Conta via IA

```bash
POST /acme/api/journal_entries/suggest-account/
{
  "description": "Pagamento de energia elétrica",
  "amount": 1500.00
}
```

Retorna sugestões de contas contábeis baseadas em embeddings e histórico de classificação.

### Histórico de Classificação

```bash
GET /acme/api/journal_entries/classification-history/?description=energia
```

Retorna como descrições similares foram classificadas anteriormente.

### Derivação de Lançamentos

```bash
POST /acme/api/journal_entries/derive_from/
{
  "source_id": 42,
  "adjustments": {"amount": 1200.00}
}
```

Cria um novo lançamento baseado em um existente.

---

## 5.4 Moedas (Currencies)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `code` | string | Código ISO (BRL, USD, EUR) |
| `name` | string | Nome completo |
| `symbol` | string | Símbolo (R$, $, €) |
| `cliente_erp_id` | string | ID no ERP externo |

```bash
# Listar moedas
GET /api/core/currencies/

# Criar moeda
POST /api/core/currencies/
{"code": "BRL", "name": "Real Brasileiro", "symbol": "R$"}
```

---

## 5.5 Bancos e Contas Bancárias

### Bancos (Banks)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | string | Nome do banco |
| `country` | string | País |
| `bank_code` | string | Código do banco (ex: 001 = BB) |
| `is_active` | boolean | Ativo |

### Contas Bancárias (Bank Accounts)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `entity` | FK Entity | Entidade dona |
| `bank` | FK Bank | Banco |
| `currency` | FK Currency | Moeda |
| `account_number` | string | Número da conta |
| `balance` / `balance_date` | decimal / date | Saldo e data |

### Transações Bancárias (Bank Transactions)

Transações bancárias representam movimentações no extrato do banco. São usadas na conciliação para cruzar com lançamentos contábeis.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `bank_account` | FK BankAccount | Conta bancária |
| `date` | date | Data da movimentação |
| `amount` | decimal | Valor (positivo = entrada, negativo = saída) |
| `description` | text | Descrição do extrato |
| `status` | choice | Status de conciliação |
| `tag` | string | Tag livre para agrupamento na conciliação |
| `cliente_erp_id` | string | ID no ERP externo |

### Filtros de Transações Bancárias

```bash
# Filtrar por tag
GET /acme/api/bank_transactions/?tag=revisar

# Filtrar por ID ERP
GET /acme/api/bank_transactions/?cliente_erp_id=ERP-BK-001
```

### Endpoints de Transações Bancárias

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/{tenant}/api/bank_transactions/` | Listar |
| `POST` | `/{tenant}/api/bank_transactions/` | Criar |
| `POST` | `/{tenant}/api/bank_transactions/bulk_create/` | Criar em lote |
| `POST` | `/{tenant}/api/bank_transactions/{id}/match_boletos/` | Vincular boletos |
| `POST` | `/{tenant}/api/bank_transactions/suggest_matches/` | Sugerir correspondências |

> **Dica:** Para importar extratos bancários em massa, use o [Pipeline ETL](11-etl-importacao.md) com o modelo alvo `BankTransaction`.

---

## 5.6 Centros de Custo (Cost Centers)

Centros de custo permitem classificar transações por departamento, projeto ou centro de responsabilidade.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | string | Nome do centro de custo |
| `center_type` | choice | Tipo (custo, lucro, investimento) |
| `balance` / `balance_date` | decimal / date | Saldo e data |

### Alocações (Allocation Bases)

Definem como custos são rateados entre centros:

```bash
POST /acme/api/cost_centers/
{"name": "TI", "center_type": "cost"}

# Criar alocação: 60% TI, 40% Comercial
POST /acme/api/allocation-bases/
[
  {"cost_center": 1, "profit_center": 2, "percentage": 60, "month": "2026-04"},
  {"cost_center": 1, "profit_center": 3, "percentage": 40, "month": "2026-04"}
]
```

---

## 5.7 Histórico de Saldos (Balance History)

O sistema mantém um histórico mensal de saldos por conta, permitindo consultas rápidas de demonstrações financeiras.

### Consulta

```bash
GET /acme/api/balance-history/?account=5&year=2026
```

### Recálculo

Quando necessário recalcular o histórico:

```bash
POST /acme/api/balance-history/recalculate/
```

> **Atenção:** O recálculo é processado em background via Celery e pode levar vários minutos para grandes volumes.

---

## 5.8 Resumo de Conta (Account Summary)

Para uma visão consolidada de movimentação por conta:

```bash
GET /acme/account_summary/?entity=1&date_from=2026-01-01&date_to=2026-03-31
```

Retorna saldo inicial, total de débitos, total de créditos e saldo final por conta no período.

---

## 5.9 Comparação Banco vs Livro (Bank Book Daily Balances)

A API de saldos diários compara o extrato bancário com os lançamentos contábeis dia a dia, facilitando a identificação de divergências entre banco e contabilidade.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|:-----------:|-----------|
| `date_from` | date | Sim | Data inicial do período |
| `date_to` | date | Sim | Data final do período |
| `bank_account_id` | int | Não | ID de uma conta bancária específica (sem este filtro, retorna visão agregada por moeda) |

### Exemplo 1: Visão agregada (todas as contas, por moeda)

```bash
GET /acme/api/bank-book-daily-balances/?date_from=2026-03-01&date_to=2026-03-31
```

**Resposta:**

```json
{
  "bank_accounts": [
    {"id": 1, "name": "Banco do Brasil C/C", "currency": "BRL"},
    {"id": 2, "name": "Itaú C/C", "currency": "BRL"}
  ],
  "aggregate": {
    "BRL": [
      {"date": "2026-03-01", "bank_balance": 150000.00, "book_balance": 148500.00, "difference": 1500.00},
      {"date": "2026-03-02", "bank_balance": 155000.00, "book_balance": 155000.00, "difference": 0.00},
      {"date": "2026-03-03", "bank_balance": 142000.00, "book_balance": 143200.00, "difference": -1200.00}
    ]
  }
}
```

> A diferença positiva indica saldo maior no banco; negativa indica saldo maior na contabilidade.

### Exemplo 2: Detalhamento por conta bancária

```bash
GET /acme/api/bank-book-daily-balances/?date_from=2026-03-01&date_to=2026-03-05&bank_account_id=1
```

**Resposta:**

```json
{
  "bank_accounts": [{"id": 1, "name": "Banco do Brasil C/C", "currency": "BRL"}],
  "bank": [
    {"date": "2026-03-01", "movement": 5000.00, "running_balance": 105000.00},
    {"date": "2026-03-02", "movement": -2000.00, "running_balance": 103000.00},
    {"date": "2026-03-03", "movement": 0, "running_balance": 103000.00}
  ],
  "book": [
    {"date": "2026-03-01", "movement": 5000.00, "running_balance": 104500.00},
    {"date": "2026-03-02", "movement": -2000.00, "running_balance": 102500.00},
    {"date": "2026-03-03", "movement": 1200.00, "running_balance": 103700.00}
  ]
}
```

> No modo detalhado, `bank` mostra os movimentos diários do extrato e `book` os lançamentos contábeis vinculados à mesma conta bancária. Compare as duas linhas para identificar em quais dias ocorrem divergências.

### Uso Típico

1. **Visão geral:** Consulte sem `bank_account_id` para ver a diferença total por moeda
2. **Investigação:** Quando a diferença for relevante, filtre por `bank_account_id` para ver o detalhamento dia a dia
3. **Cruzamento:** Compare as datas com divergência com as pendências da conciliação bancária

---

## 5.10 Embeddings e Busca Semântica

O módulo de contabilidade suporta **embeddings vetoriais** para busca semântica em transações e contas.

### Verificar Saúde dos Embeddings

```bash
GET /acme/embeddings/health/
```

### Contar Registros sem Embedding

```bash
GET /acme/embeddings/missing-counts/
```

### Preencher Embeddings Faltantes

```bash
POST /acme/embeddings/backfill/
```

### Busca Semântica

```bash
POST /acme/embeddings/search/
{"query": "pagamento de energia", "model": "Transaction", "limit": 10}
```

> **Avançado:** Embeddings são usados internamente pela conciliação bancária para encontrar correspondências entre transações bancárias e lançamentos contábeis.

---

*Anterior: [04 — Multi-Tenancy e Usuários](04-multitenancy-usuarios.md) · Próximo: [06 — Conciliação Bancária](06-conciliacao-bancaria.md)*

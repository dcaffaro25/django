# 11 — Importação de Dados (Pipeline ETL)

O pipeline ETL (Extract, Transform, Load) permite importar dados de planilhas Excel para qualquer modelo da plataforma, com transformação, validação e visualização prévia dos dados.

---

## 11.1 Visão Geral do Pipeline

O processo de importação segue 6 etapas:

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ 1.Upload │──►│2.Análise │──►│3.Preview │──►│4.Transf. │──►│5.Valid.  │──►│6.Import  │
│ do Excel │   │ Colunas  │   │ Dados    │   │ Regras   │   │ Errors   │   │ Persistir│
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

1. **Upload** — Envio do arquivo Excel (.xlsx, .xls)
2. **Análise** — Detecção de colunas, tipos de dados e mapeamento para campos do modelo
3. **Preview** — Visualização dos dados transformados antes de importar
4. **Transformação** — Aplicação de regras de substituição, conversões e mapeamentos
5. **Validação** — Verificação de erros, duplicatas e restrições
6. **Importação** — Persistência dos dados no banco

---

## 11.2 Modelos Disponíveis para Importação

Para ver todos os modelos que podem receber dados via ETL:

```bash
GET /acme/api/core/etl/transformation-rules/available_models/
```

**Modelos mais comuns:**

| Modelo | Descrição | Uso Típico |
|--------|-----------|------------|
| `Account` | Plano de contas | Migração inicial de ERP |
| `Transaction` | Transações | Importação de movimentações |
| `JournalEntry` | Lançamentos contábeis | Importação de razão contábil |
| `BankTransaction` | Transações bancárias | Importação de extrato OFX/Excel |
| `BusinessPartner` | Parceiros comerciais | Cadastro de clientes/fornecedores |
| `ProductService` | Produtos e serviços | Catálogo de produtos |
| `Employee` | Funcionários | Cadastro de RH |
| `CostCenter` | Centros de custo | Estrutura de custos |

---

## 11.3 Passo a Passo — Análise

### Etapa 1: Analisar o Arquivo

Envie o Excel para análise antes de importar:

```bash
POST /acme/api/core/etl/analyze/
Content-Type: multipart/form-data

file: planilha.xlsx
target_model: Transaction
sheet_name: Movimentações
header_row: 0
```

**Parâmetros:**

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `file` | file | Arquivo Excel |
| `target_model` | string | Modelo alvo |
| `sheet_name` | string | Nome da aba (opcional — usa a primeira) |
| `header_row` | int | Linha do cabeçalho (0-indexed, padrão: 0) |

**Resposta:**

```json
{
  "columns": ["Data", "Descrição", "Valor", "Moeda", "Entidade"],
  "row_count": 1500,
  "sample_data": [...],
  "target_fields": [
    {"name": "date", "type": "date", "required": true},
    {"name": "description", "type": "string", "required": false},
    {"name": "amount", "type": "decimal", "required": true},
    {"name": "currency", "type": "fk", "required": true},
    {"name": "entity", "type": "fk", "required": true}
  ],
  "suggested_mappings": {
    "Data": "date",
    "Descrição": "description",
    "Valor": "amount"
  }
}
```

---

## 11.4 Regras de Transformação

### Criando uma Regra de Transformação

Regras de transformação definem como colunas do Excel mapeiam para campos do modelo:

```bash
POST /acme/api/core/etl/transformation-rules/
{
  "name": "Importação Transações ERP",
  "target_model": "Transaction",
  "company": 1,
  "sheet_config": {
    "sheet_name": "Movimentações",
    "header_row": 0,
    "skip_rows": []
  },
  "column_mappings": {
    "Data Movimento": "date",
    "Histórico": "description",
    "Valor (R$)": "amount",
    "Código Moeda": "currency__code",
    "Filial": "entity__name"
  },
  "default_values": {
    "state": "draft"
  },
  "transformations": {
    "date": {"format": "%d/%m/%Y"},
    "amount": {"decimal_separator": ",", "thousands_separator": "."}
  }
}
```

### Campos da Regra

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | string | Nome descritivo |
| `target_model` | string | Modelo destino |
| `company` | FK | Empresa |
| `sheet_config` | JSON | Configuração da aba (nome, cabeçalho) |
| `column_mappings` | JSON | Mapeamento coluna→campo |
| `default_values` | JSON | Valores padrão para campos não mapeados |
| `transformations` | JSON | Transformações por campo (formato de data, decimais, etc.) |

### Mapeamento de FKs

Para campos de chave estrangeira, use a notação `campo__lookup`:

| Notação | Significado | Exemplo |
|---------|-------------|---------|
| `currency__code` | Busca Currency pelo código | `"BRL"` → Currency(code="BRL") |
| `entity__name` | Busca Entity pelo nome | `"Filial SP"` → Entity(name="Filial SP") |
| `account__account_code` | Busca Account pelo código | `"1.1.1"` → Account(account_code="1.1.1") |

---

## 11.4b Identificação por ID Externo (ERP)

Além de IDs internos, o pipeline de importação suporta o uso de **IDs do ERP externo** (`cliente_erp_id`) para identificar registros existentes e resolver chaves estrangeiras. Isso é essencial para integrações contínuas com ERPs como Omie, SAP, etc.

### Coluna Especial `__erp_id` (Upsert/Delete por ID ERP)

Adicione a coluna `__erp_id` na planilha para que o sistema identifique registros por `cliente_erp_id`:

| `__erp_id` | Comportamento |
|-------------|---------------|
| `ERP-123` | Se existe um registro com `cliente_erp_id = "ERP-123"`, **atualiza**. Caso contrário, **cria** o registro. |
| `-ERP-123` | **Exclui** o registro com `cliente_erp_id = "ERP-123"` (prefixo `-`). |
| _(vazio)_ | **Cria** um novo registro (comportamento padrão). |

**Exemplo de planilha com `__erp_id`:**

| __erp_id | date | description | amount | currency_erp_id |
|----------|------|-------------|--------|-----------------|
| TX-001 | 2026-03-15 | Pagamento NF 123 | 5000.00 | BRL-01 |
| TX-002 | 2026-03-16 | Recebimento cliente | 12000.00 | BRL-01 |
| -TX-003 | | | | |

Neste exemplo:
- **TX-001:** Se já existe uma transação com `cliente_erp_id = "TX-001"`, atualiza seus campos. Senão, cria uma nova.
- **TX-002:** Mesmo comportamento de upsert.
- **-TX-003:** Exclui a transação com `cliente_erp_id = "TX-003"`.

### Coluna `__row_id` (Upsert/Delete por ID Interno)

O `__row_id` funciona da mesma forma, mas usando o **ID interno** (PK) do sistema:

| `__row_id` | Comportamento |
|-------------|---------------|
| `42` | Atualiza o registro com `id = 42` |
| `-42` | Exclui o registro com `id = 42` |
| _(vazio)_ | Cria um novo registro |

> **Quando usar qual:** Use `__erp_id` quando os dados vêm de um sistema externo (ERP) e você possui o identificador externo. Use `__row_id` quando já conhece os IDs internos da plataforma Nord.

### Resolução de FK por ID ERP (`*_erp_id`)

Além de identificar o próprio registro, você pode referenciar **chaves estrangeiras** pelo `cliente_erp_id` do registro relacionado. Use o sufixo `_erp_id` no nome da coluna:

| Coluna na Planilha | Significado |
|---------------------|-------------|
| `account_erp_id` | Resolve `account_id` buscando Account com `cliente_erp_id = valor` |
| `entity_erp_id` | Resolve `entity_id` buscando Entity com `cliente_erp_id = valor` |
| `currency_erp_id` | Resolve `currency_id` buscando Currency com `cliente_erp_id = valor` |
| `bank_account_erp_id` | Resolve `bank_account_id` buscando BankAccount com `cliente_erp_id = valor` |
| `transaction_erp_id` | Resolve `transaction_id` buscando Transaction com `cliente_erp_id = valor` |
| `cost_center_erp_id` | Resolve `cost_center_id` buscando CostCenter com `cliente_erp_id = valor` |

**Exemplo:** Importar lançamentos contábeis usando IDs do ERP para referenciar a conta e transação:

| __erp_id | account_erp_id | transaction_erp_id | debit_amount | credit_amount |
|----------|----------------|---------------------|--------------|---------------|
| JE-001 | CONTA-1101 | TX-001 | 5000.00 | 0 |
| JE-002 | CONTA-2101 | TX-001 | 0 | 5000.00 |

Neste exemplo:
- `account_erp_id = "CONTA-1101"` → busca a conta contábil com `cliente_erp_id = "CONTA-1101"` e usa seu `id` como `account_id`
- `transaction_erp_id = "TX-001"` → busca a transação com `cliente_erp_id = "TX-001"` e usa seu `id` como `transaction_id`

> **Dica:** A resolução por `*_erp_id` pode ser combinada com resolução por caminho (`account__account_code`) na mesma planilha. O `*_erp_id` tem prioridade quando ambos estão preenchidos.

### Exemplo Completo: Importar Transações e JEs via ID ERP

**Passo 1 — Prepare a planilha com a aba "Transaction":**

| __erp_id | cliente_erp_id | date | due_date | description | amount | currency_erp_id | entity_erp_id | nf_number |
|----------|----------------|------|----------|-------------|--------|-----------------|---------------|-----------|
| TX-100 | TX-100 | 2026-03-15 | 2026-04-15 | Pagamento NF 456 | 5000.00 | MOEDA-BRL | FILIAL-SP | 000456 |
| TX-101 | TX-101 | 2026-03-16 | 2026-04-16 | Recebimento NF 789 | 12000.00 | MOEDA-BRL | FILIAL-RJ | 000789 |

**Passo 2 — Prepare a aba "JournalEntry":**

| __erp_id | transaction_erp_id | account_erp_id | debit_amount | credit_amount |
|----------|---------------------|----------------|--------------|---------------|
| JE-200 | TX-100 | DESP-ALUG | 5000.00 | 0 |
| JE-201 | TX-100 | BANCO-BB | 0 | 5000.00 |
| JE-202 | TX-101 | BANCO-ITAU | 12000.00 | 0 |
| JE-203 | TX-101 | REC-CLIENTES | 0 | 12000.00 |

**Passo 3 — Importe usando o template:**
```bash
POST /acme/api/core/import/
Content-Type: multipart/form-data

file: importacao_erp.xlsx
```

**Resultado esperado:**
- 2 transações criadas (ou atualizadas se `TX-100`/`TX-101` já existiam)
- 4 lançamentos contábeis criados, cada um vinculado à transação correspondente via `transaction_erp_id`
- FKs de conta, moeda e entidade resolvidos automaticamente pelo `cliente_erp_id` de cada modelo

---

## 11.5 Preview (Visualização Prévia)

Antes de importar definitivamente, visualize o resultado:

```bash
POST /acme/api/core/etl/preview/
Content-Type: multipart/form-data

file: planilha.xlsx
transformation_rule_id: 1
```

**Resposta:**

```json
{
  "total_rows": 1500,
  "valid_rows": 1480,
  "error_rows": 20,
  "preview": [
    {
      "row": 1,
      "data": {"date": "2026-03-15", "description": "Pagamento NF 123", "amount": 5000.00},
      "status": "valid"
    },
    {
      "row": 15,
      "data": {"date": null, "description": "...", "amount": "abc"},
      "status": "error",
      "errors": ["date: formato inválido", "amount: não é um número"]
    }
  ],
  "warnings": [
    "20 linhas com erros serão ignoradas",
    "3 registros possivelmente duplicados encontrados"
  ]
}
```

> **Dica:** Sempre faça o preview antes de executar a importação. Corrija erros na planilha e reimporte.

---

## 11.6 Executando a Importação

```bash
POST /acme/api/core/etl/execute/
Content-Type: multipart/form-data

file: planilha.xlsx
transformation_rule_id: 1
```

**Resposta:**

```json
{
  "status": "completed",
  "total_rows": 1500,
  "imported": 1480,
  "errors": 20,
  "created": 1200,
  "updated": 280,
  "log_id": 42
}
```

### Relatório de Erros

Se houve erros, consulte o relatório detalhado:

```bash
GET /acme/api/core/etl/logs/42/error-report/
```

---

## 11.7 Logs de Importação

Cada importação gera um log que pode ser consultado:

```bash
# Listar logs de importação
GET /acme/api/core/etl/logs/

# Detalhe de um log
GET /acme/api/core/etl/logs/{id}/
```

**Campos do log:**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `file_name` | string | Nome do arquivo importado |
| `status` | choice | `completed`, `failed`, `partial` |
| `total_rows` | int | Total de linhas |
| `imported_rows` | int | Linhas importadas com sucesso |
| `error_rows` | int | Linhas com erro |
| `errors` | JSON | Detalhamento dos erros |
| `warnings` | JSON | Avisos |

---

## 11.8 Pipeline com Regras de Substituição

O ETL pode ser combinado com [regras de substituição](13-regras-automacao.md) para normalizar dados durante a importação.

### Fluxo

```
Excel → Mapeamento de Colunas → Regras de Substituição → Validação → Importação
```

### Exemplo

Seu ERP exporta centros de custo como `"CC-001 TI"`, mas no sistema o nome é `"Tecnologia da Informação"`.

**1. Crie a regra de substituição:**
```bash
POST /acme/api/core/substitution-rules/
{
  "model_name": "Transaction",
  "field_name": "cost_center",
  "match_type": "startswith",
  "match_value": "CC-001",
  "substitution_value": "Tecnologia da Informação"
}
```

**2. Na importação, as regras são aplicadas automaticamente.**

---

## 11.9 Importação via Interface HTML

Além da API, existe uma interface HTML para importação:

```
https://servidor.com/acme/etl/preview/   → Upload e preview
https://servidor.com/acme/etl/execute/   → Executar importação
```

---

## 11.10 Fluxo Completo — Importar Extrato Bancário

### Cenário

Você tem um extrato bancário em Excel com colunas: `Data`, `Histórico`, `Valor`, `Saldo`.

**Passo 1 — Analisar:**
```bash
POST /acme/api/core/etl/analyze/
file: extrato_banco_mar2026.xlsx
target_model: BankTransaction
```

**Passo 2 — Criar regra de transformação:**
```bash
POST /acme/api/core/etl/transformation-rules/
{
  "name": "Extrato BB C/C",
  "target_model": "BankTransaction",
  "column_mappings": {
    "Data": "date",
    "Histórico": "description",
    "Valor": "amount"
  },
  "default_values": {
    "bank_account": 1,
    "currency": 1,
    "status": "unreconciled"
  },
  "transformations": {
    "date": {"format": "%d/%m/%Y"},
    "amount": {"decimal_separator": ",", "thousands_separator": "."}
  }
}
```

**Passo 3 — Preview:**
```bash
POST /acme/api/core/etl/preview/
file: extrato_banco_mar2026.xlsx
transformation_rule_id: 5
```

**Passo 4 — Importar:**
```bash
POST /acme/api/core/etl/execute/
file: extrato_banco_mar2026.xlsx
transformation_rule_id: 5
```

**Passo 5 — Verificar:**
```bash
GET /acme/api/bank_transactions/?bank_account=1&date_after=2026-03-01
```

---

## 11.10b Fluxo Completo — Importação via Template com IDs ERP

### Cenário

Sua empresa usa o ERP Omie e cada registro já tem um identificador (`cliente_erp_id`). Você quer importar transações e lançamentos contábeis usando os IDs do Omie para vincular registros, e quer que importações futuras atualizem os registros existentes automaticamente.

**Passo 1 — Baixar o template de importação:**
```bash
GET /acme/api/core/import/template/
```

O template Excel contém:
- Uma aba por modelo (Transaction, JournalEntry, BankTransaction, etc.)
- Uma aba **ImportHelp** com documentação das colunas especiais

**Passo 2 — Preencher a aba Transaction:**

| __erp_id | cliente_erp_id | date | due_date | description | amount | currency_erp_id | entity_erp_id | nf_number |
|----------|----------------|------|----------|-------------|--------|-----------------|---------------|-----------|
| OMIE-CP-001 | OMIE-CP-001 | 2026-03-10 | 2026-04-10 | Conta de Luz - Março | 2500.00 | BRL | FILIAL-01 | 000123 |
| OMIE-CP-002 | OMIE-CP-002 | 2026-03-15 | 2026-04-15 | Aluguel Escritório | 8000.00 | BRL | FILIAL-01 | |
| OMIE-CR-001 | OMIE-CR-001 | 2026-03-20 | 2026-05-20 | Venda Produto X | 15000.00 | BRL | FILIAL-02 | 000456 |

**Passo 3 — Preencher a aba JournalEntry:**

| __erp_id | transaction_erp_id | account_erp_id | cost_center_erp_id | debit_amount | credit_amount |
|----------|---------------------|----------------|---------------------|--------------|---------------|
| JE-CP1-D | OMIE-CP-001 | DESP-ENERGIA | CC-ADM | 2500.00 | 0 |
| JE-CP1-C | OMIE-CP-001 | BANCO-BB | | 0 | 2500.00 |
| JE-CP2-D | OMIE-CP-002 | DESP-ALUGUEL | CC-ADM | 8000.00 | 0 |
| JE-CP2-C | OMIE-CP-002 | BANCO-BB | | 0 | 8000.00 |

**Passo 4 — Importar:**
```bash
POST /acme/api/core/import/
Content-Type: multipart/form-data

file: importacao_omie.xlsx
```

**Resultado esperado (1ª importação):**
```json
{
  "Transaction": {"created": 3, "updated": 0, "deleted": 0},
  "JournalEntry": {"created": 4, "updated": 0, "deleted": 0}
}
```

**Passo 5 — Re-importar com alterações (atualização automática):**

Altere a planilha — por exemplo, corrija o valor da conta de luz:

| __erp_id | cliente_erp_id | date | due_date | description | amount | currency_erp_id | entity_erp_id | nf_number |
|----------|----------------|------|----------|-------------|--------|-----------------|---------------|-----------|
| OMIE-CP-001 | OMIE-CP-001 | 2026-03-10 | 2026-04-10 | Conta de Luz - Março (corrigida) | 2750.00 | BRL | FILIAL-01 | 000123 |

**Resultado esperado (2ª importação):**
```json
{
  "Transaction": {"created": 0, "updated": 1, "deleted": 0}
}
```

> O registro com `cliente_erp_id = "OMIE-CP-001"` foi encontrado e atualizado, sem criar duplicatas.

**Passo 6 — Excluir um registro via planilha:**

| __erp_id |
|----------|
| -OMIE-CP-002 |

**Resultado esperado:**
```json
{
  "Transaction": {"created": 0, "updated": 0, "deleted": 1}
}
```

> O prefixo `-` no `__erp_id` indica exclusão. A transação com `cliente_erp_id = "OMIE-CP-002"` é removida.

---

## 11.11 Dicas e Boas Práticas

### Preparação da Planilha

- Certifique-se de que a **primeira linha** contém os cabeçalhos
- Remova linhas em branco e formatação especial
- Padronize formatos de data e números
- Evite células mescladas

### Performance

- Para planilhas com mais de 10.000 linhas, a importação roda em background via Celery
- Divida planilhas muito grandes em partes menores
- Reutilize regras de transformação para importações recorrentes

### Troubleshooting

| Problema | Solução |
|----------|---------|
| Erros de formato de data | Ajuste `transformations.date.format` |
| Valores numéricos incorretos | Configure separadores decimal/milhar |
| FK não encontrado | Verifique o lookup field, use `*_erp_id` ou crie regras de substituição |
| `*_erp_id` não resolve FK | Confirme que o registro relacionado existe e tem o `cliente_erp_id` preenchido |
| `__erp_id` não encontra registro | Confirme que o modelo tem o campo `cliente_erp_id` e que o valor corresponde |
| Duplicatas | Use `__erp_id` ou `__row_id` para atualizar registros existentes em vez de criar novos |
| Timeout | Reduza o tamanho da planilha ou verifique Celery |

---

*Anterior: [10 — Estoque](10-estoque.md) · Próximo: [12 — Integrações ERP](12-integracoes-erp.md)*

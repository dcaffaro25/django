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

Além de IDs internos, o pipeline de importação suporta o uso de **IDs do ERP externo** (`erp_id`) para identificar registros existentes e resolver chaves estrangeiras. Isso é essencial para integrações contínuas com ERPs como Omie, SAP, etc.

### Coluna Especial `__erp_id` (Upsert/Delete por ID ERP)

Adicione a coluna `__erp_id` na planilha para que o sistema identifique registros por `erp_id`:

| `__erp_id` | Comportamento |
|-------------|---------------|
| `ERP-123` | Se existe um registro com `erp_id = "ERP-123"`, **atualiza**. Caso contrário, **cria** o registro. |
| `-ERP-123` | **Exclui** o registro com `erp_id = "ERP-123"` (prefixo `-`). |
| _(vazio)_ | **Cria** um novo registro (comportamento padrão). |

**Coluna `erp_id` mapeada (import em massa / ETL):** Nos modelos que definem o campo `erp_id`, você pode enviar o identificador externo em uma coluna mapeada para `erp_id`. Com `erp_key_coalesce` ativo (padrão em `ImportTransformationRule`), essa coluna equivale à chave de upsert/delete usada por `__erp_id`. Se `__erp_id` e `erp_id` aparecerem na mesma linha, os valores precisam coincidir.

**Exemplo de planilha com `__erp_id`:**

| __erp_id | date | description | amount | currency_erp_id |
|----------|------|-------------|--------|-----------------|
| TX-001 | 2026-03-15 | Pagamento NF 123 | 5000.00 | BRL-01 |
| TX-002 | 2026-03-16 | Recebimento cliente | 12000.00 | BRL-01 |
| -TX-003 | | | | |

Neste exemplo:
- **TX-001:** Se já existe uma transação com `erp_id = "TX-001"`, atualiza seus campos. Senão, cria uma nova.
- **TX-002:** Mesmo comportamento de upsert.
- **-TX-003:** Exclui a transação com `erp_id = "TX-003"`.

### Coluna `__row_id` (Upsert/Delete por ID Interno)

O `__row_id` funciona da mesma forma, mas usando o **ID interno** (PK) do sistema:

| `__row_id` | Comportamento |
|-------------|---------------|
| `42` | Atualiza o registro com `id = 42` |
| `-42` | Exclui o registro com `id = 42` |
| _(vazio)_ | Cria um novo registro |

> **Quando usar qual:** Use `__erp_id` quando os dados vêm de um sistema externo (ERP) e você possui o identificador externo. Use `__row_id` quando já conhece os IDs internos da plataforma Nord.

### Resolução de FK por ID ERP (`*_erp_id`)

Além de identificar o próprio registro, você pode referenciar **chaves estrangeiras** pelo `erp_id` do registro relacionado. Use o sufixo `_erp_id` no nome da coluna:

**Convenção:**

- **`erp_id`** (sem prefixo de FK): grava o identificador externo **no registro que está sendo importado** (campo `erp_id` desse modelo).
- **`<campo_fk>_erp_id`**: o trecho antes de `_erp_id` deve ser o **nome do campo `ForeignKey`** no modelo de destino (por exemplo, em `Transaction` o FK `entity` → coluna `entity_erp_id`). O valor informado é comparado com o campo `erp_id` do modelo relacionado (`Entity`, `Account`, etc.) para preencher `<campo_fk>_id`.

| Coluna na Planilha | Significado |
|---------------------|-------------|
| `account_erp_id` | Resolve `account_id` buscando Account com `erp_id = valor` |
| `entity_erp_id` | Resolve `entity_id` buscando Entity com `erp_id = valor` |
| `currency_erp_id` | Resolve `currency_id` buscando Currency com `erp_id = valor` |
| `bank_account_erp_id` | Resolve `bank_account_id` buscando BankAccount com `erp_id = valor` |
| `transaction_erp_id` | Resolve `transaction_id` buscando Transaction com `erp_id = valor` |
| `cost_center_erp_id` | Resolve `cost_center_id` buscando CostCenter com `erp_id = valor` |

**Exemplo:** Importar lançamentos contábeis usando IDs do ERP para referenciar a conta e transação:

| __erp_id | account_erp_id | transaction_erp_id | debit_amount | credit_amount |
|----------|----------------|---------------------|--------------|---------------|
| JE-001 | CONTA-1101 | TX-001 | 5000.00 | 0 |
| JE-002 | CONTA-2101 | TX-001 | 0 | 5000.00 |

Neste exemplo:
- `account_erp_id = "CONTA-1101"` → busca a conta contábil com `erp_id = "CONTA-1101"` e usa seu `id` como `account_id`
- `transaction_erp_id = "TX-001"` → busca a transação com `erp_id = "TX-001"` e usa seu `id` como `transaction_id`

> **Dica:** A resolução por `*_erp_id` pode ser combinada com resolução por caminho (`account__account_code`) na mesma planilha. O `*_erp_id` tem prioridade quando ambos estão preenchidos.

### Exemplo Completo: Importar Transações e JEs via ID ERP

**Passo 1 — Prepare a planilha com a aba "Transaction":**

| __erp_id | erp_id | date | due_date | description | amount | currency_erp_id | entity_erp_id | nf_number |
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
- FKs de conta, moeda e entidade resolvidos automaticamente pelo `erp_id` de cada modelo

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

Sua empresa usa o ERP Omie e cada registro já tem um identificador (`erp_id`). Você quer importar transações e lançamentos contábeis usando os IDs do Omie para vincular registros, e quer que importações futuras atualizem os registros existentes automaticamente.

**Passo 1 — Baixar o template de importação:**
```bash
GET /acme/api/core/import/template/
```

O template Excel contém:
- Uma aba por modelo (Transaction, JournalEntry, BankTransaction, etc.)
- Uma aba **ImportHelp** com documentação das colunas especiais

**Passo 2 — Preencher a aba Transaction:**

| __erp_id | erp_id | date | due_date | description | amount | currency_erp_id | entity_erp_id | nf_number |
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

| __erp_id | erp_id | date | due_date | description | amount | currency_erp_id | entity_erp_id | nf_number |
|----------|----------------|------|----------|-------------|--------|-----------------|---------------|-----------|
| OMIE-CP-001 | OMIE-CP-001 | 2026-03-10 | 2026-04-10 | Conta de Luz - Março (corrigida) | 2750.00 | BRL | FILIAL-01 | 000123 |

**Resultado esperado (2ª importação):**
```json
{
  "Transaction": {"created": 0, "updated": 1, "deleted": 0}
}
```

> O registro com `erp_id = "OMIE-CP-001"` foi encontrado e atualizado, sem criar duplicatas.

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

> O prefixo `-` no `__erp_id` indica exclusão. A transação com `erp_id = "OMIE-CP-002"` é removida.

---

## 11.10c Transações com o mesmo `erp_id` em múltiplas linhas

> **Regra geral:** no universo contábil, `erp_id` identifica **uma** transação econômica (uma nota fiscal, um boleto, uma transferência). Se o mesmo `erp_id` aparece em várias linhas da planilha, o sistema interpreta essas linhas como **pernas da mesma transação** — e não como transações distintas que casualmente compartilham um identificador externo.

O comportamento depende de qual dos dois modos de importação está em uso.

### 11.10c.1 Modo 1 — Abas separadas de `Transaction` + `JournalEntry`

Este é o modo usado em 11.10b: o template tem uma aba `Transaction` (campos da transação) e uma aba `JournalEntry` (campos dos lançamentos), ligadas pelo campo `__transaction_erp_id` na aba `JournalEntry`.

**A aba `Transaction` precisa ter UMA linha por `erp_id`.** Se o mesmo `erp_id` aparecer em mais de uma linha da aba `Transaction`, o sistema:

1. **Compara todos os campos de nível-transação** (`date`, `entity`, `description`, `amount`, `currency`) entre as linhas duplicadas.
2. Se **todos os campos coincidem** → trata como importação redundante e processa **uma única** transação.
3. Se **qualquer campo diverge** → rejeita as linhas duplicadas com um erro listando cada conflito encontrado.

**Exemplo — linhas duplicadas com campos idênticos (dedup silencioso):**

| __erp_id | erp_id | date | description | amount | currency_erp_id | entity_erp_id |
|----------|--------|------|-------------|--------|-----------------|---------------|
| OMIE-NF-123 | OMIE-NF-123 | 2026-04-10 | Fornecedor ABC | 5000.00 | BRL | FILIAL-01 |
| OMIE-NF-123 | OMIE-NF-123 | 2026-04-10 | Fornecedor ABC | 5000.00 | BRL | FILIAL-01 |

**Resultado:**
```json
{
  "Transaction": {"created": 1, "updated": 0, "deduped": 1}
}
```

**Exemplo — linhas duplicadas com conflito (rejeitadas):**

| __erp_id | erp_id | date | description | amount | currency_erp_id | entity_erp_id |
|----------|--------|------|-------------|--------|-----------------|---------------|
| OMIE-NF-123 | OMIE-NF-123 | 2026-04-10 | Fornecedor ABC | 5000.00 | BRL | FILIAL-01 |
| OMIE-NF-123 | OMIE-NF-123 | 2026-04-11 | Fornecedor ABC | 5500.00 | BRL | FILIAL-01 |

**Resultado:**
```json
{
  "Transaction": {"created": 0, "errors": 2},
  "errors": [
    {
      "erp_id": "OMIE-NF-123",
      "row_ids": [2, 3],
      "message": "Linhas compartilham o mesmo erp_id mas divergem em: date (2026-04-10 vs 2026-04-11), amount (5000.00 vs 5500.00)"
    }
  ]
}
```

> **Por que rejeitar em vez de eleger silenciosamente uma das linhas?** Dedupar silenciosamente transforma um erro de planilha em uma divergência oculta entre o arquivo de origem e o banco — quase sempre pior do que falhar explicitamente e forçar o operador a corrigir a fonte.

**Os vários lançamentos contábeis (JEs) vão na aba `JournalEntry`.** Cada linha ali é uma perna da transação, ligada ao pai via `__transaction_erp_id`:

| __erp_id | transaction_erp_id | account_erp_id | debit_amount | credit_amount |
|----------|--------------------|----------------|--------------|---------------|
| JE-NF123-D | OMIE-NF-123 | FORNECEDORES | 5000.00 | 0 |
| JE-NF123-C | OMIE-NF-123 | BANCO-BB | 0 | 5000.00 |

**Invariante do Modo 1:** na aba `JournalEntry`, a soma de `debit_amount` deve igualar a soma de `credit_amount` para cada `transaction_erp_id` — o sistema valida isso antes de persistir.

---

### 11.10c.2 Modo 2 — ETL com `auto_create_journal_entries` habilitado

Neste modo (ver 11.8), a planilha tem **apenas** uma aba `Transaction` com colunas para conta bancária e conta contraparte (por exemplo, `bank_account_id`, `account_path`, `amount`). O ETL cria automaticamente os lançamentos contábeis a partir de cada linha.

**Quando o mesmo `erp_id` aparece em várias linhas, o sistema agrupa:** produz **1 `Transaction`** + **N lançamentos contraparte** (um por linha) + **1 lançamento bancário agregado** (valor total do grupo).

**Por quê um lançamento bancário agregado?** Porque no mundo real o banco registra **um** movimento. Se um boleto de R$ 10.000,00 foi alocado em duas contas contábeis (R$ 7.000 em Matéria-Prima e R$ 3.000 em Frete), o banco não sabe da divisão — ele só viu R$ 10.000,00 saindo. O lado contábil tem duas pernas contraparte, mas o lado bancário é uma só.

**Exemplo — boleto multi-alocação:**

| __erp_id | bank_account_id | account_path | amount | description |
|----------|------------------|-------------------------------|--------|-------------|
| OMIE-BOL-555 | 12 | Despesas > Matéria-Prima | -7000.00 | Boleto fornecedor XYZ — MP |
| OMIE-BOL-555 | 12 | Despesas > Frete | -3000.00 | Boleto fornecedor XYZ — frete |

**Resultado:**
```json
{
  "Transaction": {"created": 1},
  "JournalEntry": {"created": 3}
}
```

No banco, isso vira:

| Transaction | erp_id | amount |
|-------------|--------|--------|
| #10001 | OMIE-BOL-555 | -10000.00 |

| JournalEntry | transaction | account | debit | credit | tipo |
|--------------|-------------|---------|-------|--------|------|
| #20001 | #10001 | Despesas > Matéria-Prima | 7000.00 | — | contraparte |
| #20002 | #10001 | Despesas > Frete | 3000.00 | — | contraparte |
| #20003 | #10001 | Banco BB | — | 10000.00 | bancária (agregada) |

Soma de débitos = 10.000,00 · Soma de créditos = 10.000,00 — transação balanceada.

**Campos da `Transaction` em modo grupo.** A transação recebe os campos da **primeira linha do grupo** para `date`, `entity`, `description`, `currency`. O campo `amount` é calculado como a **soma** dos `amount` das linhas. Se duas linhas do mesmo grupo divergirem em campos estruturais (data, entidade, moeda, conta bancária), o grupo inteiro é rejeitado com erro listando os conflitos — mesma política do Modo 1.

**Exemplo — grupo rejeitado por divergência de conta bancária:**

| __erp_id | bank_account_id | account_path | amount |
|----------|------------------|-----------------|--------|
| OMIE-BOL-555 | 12 | Despesas > MP | -7000.00 |
| OMIE-BOL-555 | **15** | Despesas > Frete | -3000.00 |

**Resultado:**
```json
{
  "Transaction": {"created": 0, "errors": 1},
  "errors": [
    {
      "erp_id": "OMIE-BOL-555",
      "row_ids": [2, 3],
      "message": "Linhas compartilham erp_id mas divergem em: bank_account_id (12 vs 15). Um mesmo erp_id representa um único movimento bancário — escolha uma conta."
    }
  ]
}
```

**Ordem das linhas importa** apenas para decidir quais valores "ganham" nos campos de nível-transação. Campos opcionais (como `je_bank_date`, `je_book_date`) podem divergir entre linhas de um mesmo grupo — o lançamento contraparte usa o valor da sua própria linha, e o lançamento bancário agregado usa o valor da primeira linha.

---

### 11.10c.3 Quando NÃO usar o mesmo `erp_id` em várias linhas

Em alguns cenários o operador pode ser tentado a reutilizar `erp_id` de formas que o sistema não suporta:

| Cenário | ❌ Não use `erp_id` compartilhado | ✅ Faça assim |
|---------|-----------------------------------|---------------|
| Dois pagamentos separados do mesmo fornecedor | Dois `erp_id` distintos (`PAG-001`, `PAG-002`) | — |
| Parcelas de um mesmo contrato | Um `erp_id` por parcela (`CONTR-123-P01`, `P02`) | — |
| Estorno que cancela outro movimento | `erp_id` do estorno é diferente do original; o vínculo é por descrição / regra | — |
| Split de conta bancária — uma transferência em duas contas contábeis | **Aqui SIM compartilhe** `erp_id` no Modo 2 | Ver 11.10c.2 |
| Fatura com múltiplos itens (várias linhas de despesa sob a mesma nota) | **Aqui SIM compartilhe** `erp_id` | Ver 11.10c.2 |

**Regra de bolso:** se houver **um único `extrato` bancário** que cobre todas as linhas, elas compartilham `erp_id`. Se forem eventos bancários separados, cada um tem seu próprio `erp_id`.

---

### 11.10c.4 Idempotência e re-importação

Em ambos os modos, **re-importar o mesmo arquivo não cria duplicatas**. O sistema:

1. Procura cada `erp_id` no banco (escopo: empresa atual).
2. Se existe → modo `update`: os campos da transação são sobrescritos pelos valores da planilha.
3. Se o erp_id é **grupo** no Modo 2 → os lançamentos filhos também são regenerados: os antigos são apagados e os novos criados a partir das linhas atualizadas da planilha. Isso mantém o grupo consistente quando a distribuição entre contas contraparte muda entre importações.
4. Se não existe → modo `create` normal.

Para **forçar criação** (impedir update sobre uma transação pré-existente), defina `erp_duplicate_behavior: "error"` nas opções da aba. O sistema vai parar na primeira colisão em vez de atualizar.

---

## 11.10d Modo interativo (v2) — template

O modo interativo é uma alternativa opcional ao fluxo clássico
"Pré-visualizar → Executar" descrito em 11.10b. A operação é a mesma
(plano de contas e regras não mudam), mas o backend mantém uma
**sessão** no servidor onde as pendências podem ser resolvidas uma por
uma antes da importação acontecer.

**Quando usar:**
- Há linhas com o mesmo `erp_id` que divergem em campos (ver 11.10c) —
  o modo clássico rejeita a importação inteira; o interativo deixa o
  operador decidir qual linha manter.
- Há colunas com valores (conta, entidade, centro de custo) que o
  banco não reconhece — o interativo permite mapear para o registro
  existente **e opcionalmente gerar uma `SubstitutionRule`** para
  próximas importações.
- Há datas inválidas ou valores inesperados em linhas específicas —
  correção inline sem mexer no arquivo fonte.

**Como ativar:** na tela `/imports/templates`, clique em **Modo
interativo (v2)** logo acima do upload. O botão "Executar para valer"
some; no seu lugar aparece **Analisar**.

### Fluxo de tela

```
┌────────────────────────────────────────────────────────────────┐
│ Modo: ( Clássico )  ( ✨ Modo interativo (v2) )                │
├────────────────────────────────────────────────────────────────┤
│ [file input]                                                   │
│ [ Analisar ]                                                   │
└────────────────────────────────────────────────────────────────┘
    │
    ▼  (sessão criada, sem pendências)
┌────────────────────────────────────────────────────────────────┐
│ ✓ Pronto para importar.                                        │
│   Transaction: 12 linhas · JournalEntry: 24 linhas             │
│                                                [ Importar ]   │
└────────────────────────────────────────────────────────────────┘

    │  (sessão criada, COM pendências)
    ▼
┌────────────────────────────────────────────────────────────────┐
│ ⚠ Existem problemas que precisam ser resolvidos…               │
│                                                [ Importar ]   │
│                                                (desabilitado) │
│                                                                │
│ ℹ Substituições aplicadas                                      │
│   [entity: "ACME" → "ACME LTDA"]  [account: "X" → "Y"]         │
│                                                                │
│ ⚠ Conflitos de erp_id (1)                                      │
│   ┌────────────────────────────────────────────────────────┐   │
│   │ OMIE-NF-123 em Transaction, 2 linhas.                  │   │
│   │ Campos em conflito: date (2026-04-10 vs 2026-04-11)    │   │
│   │ Manter apenas uma linha: ( row_id=r1 ) ( row_id=r2 )   │   │
│   │ [ Manter esta linha ] [ Ignorar grupo ] [ Abortar ]   │   │
│   └────────────────────────────────────────────────────────┘   │
│                                                                │
│ ⚠ Referências não mapeadas (1)                                 │
│   ┌────────────────────────────────────────────────────────┐   │
│   │ "Fornecedor ABC" em JournalEntry.entity_name —         │   │
│   │ nenhum Entity correspondente.                          │   │
│   │ Mapear para: [ Entity #42 ▼ ]                          │   │
│   │ ☑ Criar regra de substituição                          │   │
│   │   Tipo: [ Exato ▼ ] Padrão: [ Fornecedor ABC ]         │   │
│   │ [ Mapear ] [ Ignorar linha ] [ Abortar ]               │   │
│   └────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

### Tipos de pendência suportados

| Tipo                       | Cartão / ações                                          |
|----------------------------|---------------------------------------------------------|
| `erp_id_conflict`          | Manter linha X / Ignorar grupo / Abortar                |
| `unmatched_reference`      | Mapear para existente + criar regra / Ignorar linha / Abortar |
| `fk_ambiguous`             | Mesma UX, candidatos pré-preenchidos no dropdown       |
| `bad_date_format`          | Corrigir inline (date picker) / Ignorar linha / Abortar |
| `negative_amount`          | Corrigir inline (número) / Ignorar linha / Abortar     |
| `missing_etl_parameter`    | Só "Editar regra" (deep-link) + "Abortar"               |

Cada cartão oferece apenas os botões declarados em `proposed_actions`
pela detecção correspondente no backend — se o tipo não aceita
"ignore_row" (ex.: `missing_etl_parameter` exige que a regra seja
corrigida upstream), o cartão não oferece essa ação.

### Passo a passo

**1. Ative o modo interativo** no toggle do topo.

**2. Selecione o arquivo** e clique **Analisar**. O backend cria uma
`ImportSession` no servidor e retorna-a com status:
- `ready` — nenhuma pendência, pode importar direto.
- `awaiting_resolve` — há diagnósticos abertos; o botão "Importar"
  fica desabilitado até você resolvê-los (ou descartá-los explicitamente).
- `error` — o arquivo não pôde ser lido (XLSX inválido, por exemplo).

**3. Resolva cada cartão.** Os cartões são independentes — você
pode resolver na ordem que quiser. Cada resolução é um POST ao
backend que **re-roda a detecção** sobre a nova versão do payload;
uma pendência pode desaparecer após resolver outra (ex.: mapear uma
conta pode eliminar todas as outras não-mapeadas que dependiam dela).

**4. Clique "Importar"** quando o cabeçalho da sessão estiver verde
("Pronto para importar"). O backend:
- Materializa qualquer `SubstitutionRule` marcada em "criar regra"
  (uma linha real em `substitution_rules`, marcada com
  `source="import_session"` para auditoria).
- Grava todos os registros no banco, dentro de uma transação
  atômica — se qualquer erro ocorrer no meio, nada é persistido e a
  sessão passa a status `error` com o motivo no campo `result`.

**5. (Opcional) Descartar** se mudar de ideia: botão "Descartar
sessão" limpa os bytes armazenados no servidor e invalida o
`session_id`. Faça isso se a pendência for grande demais para resolver
interativamente — corrija na planilha e comece uma nova análise.

### Processamento assíncrono (Celery)

Tanto `analyze` quanto `commit` são executados em **workers Celery**
(fase 6.z-a). O request HTTP responde `202 Accepted` imediatamente
com a sessão em `analyzing` (ou `committing` no caso do commit); o
frontend faz polling em `GET /sessions/<id>/` até o status sair do
estado não-terminal.

- Não há mais teto de 300s (timeout do gunicorn). O limite é o
  `CELERY_TASK_TIME_LIMIT`, que por padrão é **30 minutos** (fase
  6.z-f — era 10 min, insuficiente para importações grandes).
- Em dev/testes sem `REDIS_URL`, o Celery roda em modo `eager` —
  `.delay()` vira chamada inline, então o comportamento é
  indistinguível do modo síncrono antigo.
- **Sessões órfãs** (worker morreu, container reiniciou): a partir
  da fase 6.z-f, uma tarefa periódica (`imports_v2.reap_stale_sessions`,
  roda a cada 5 min) flipa sessões paradas em `analyzing` /
  `committing` por mais que o limite + 60s para `error` com
  `result.stage = "timeout"`. O operador pode descartar e reiniciar.

### Feedback de progresso ao vivo (fase 6.z-e)

O worker escreve um snapshot em `session.progress` nas transições de
estágio, e o frontend renderiza uma faixa com barra + contador de
erros no topo do painel de diagnóstico.

Campos observados:

- `stage`: `parsing` → `detecting` → `dry_run` → `materializing_rules` → `writing` → `done`
- `sheets_done` / `sheets_total`: percentual de abas processadas
- `current_sheet`: nome da aba que o worker está lendo/escrevendo agora
- `errors_so_far`: erros detectados até o momento (surfacia em âmbar)
- `updated_at`: timestamp ISO; o strip mostra "atualizado há 3s" etc.

A partir da fase 6.z-g, o commit **também** mostra progresso por
linha ao vivo. O worker publica atualizações a cada 100 linhas em um
canal Redis (o mesmo broker do Celery) que contorna a transação do
banco. A faixa mostra, por exemplo, `Transaction · 1.847 / 5.000
linhas · 34%` enquanto o worker está escrevendo.

Quando o Redis **não** está disponível (dev sem `REDIS_URL`,
problemas de rede), o canal falha silenciosamente e a UI volta ao
comportamento da 6.z-e — apenas progresso em nível de estágio
("Escrevendo no banco…" sem detalhe por linha). Isso é por design:
o progresso é best-effort, a importação sempre ganha.

### Performance de importações grandes

Fase 6.z-f resolveu um bug de performance: a versão v2 não estava
passando o `LookupCache` para o `execute_import_job`, causando uma
consulta de banco por FK por linha (milhares de round-trips em
planilhas grandes). Agora o cache é carregado uma vez por commit
(Account / Entity / Currency indexados em memória), o que
normalmente reduz o tempo de importação de minutos para segundos.

Para arquivos muito grandes (10k+ linhas):

- Acompanhe o painel de progresso — se o `stage` ficar em
  `materializing_rules` ou `writing` por mais que um minuto sem
  mudança em `updated_at`, algo travou e a próxima rodada do reaper
  vai limpar a sessão.
- Se o commit consistently demora mais que 30 min, aumente
  `CELERY_TASK_TIME_LIMIT` via variável de ambiente
  (`CELERY_TASK_TIME_LIMIT=60` sobe para 1h).

### Reuso de substituições (fase 6.z-d)

Na fase analyze, o backend aplica as regras de substituição uma vez
e salva o resultado em `parsed_payload["sheets_post_substitution"]`
junto com um hash das regras ativas (`substitution_revision`). No
commit, se (a) o hash ainda bate e (b) nenhuma resolução foi
registrada, o backend pula a segunda passada de substituições (a
`apply_substitutions` é idempotente sobre sua própria saída, então
mesmo que o cache fique stale em um cenário imprevisto o resultado
é o mesmo — só pagamos uma passada a mais).

Quando o cache NÃO é reutilizado:

- Operador adicionou/editou uma regra de substituição entre analyze
  e commit (hash muda → cache invalidado).
- Operador aplicou alguma resolução na sessão (edit_value em
  particular pode mutar linhas; cache invalidado por segurança).

### Idempotência

Re-analisar o mesmo arquivo cria **uma sessão nova** (o backend não
dedupa por `file_hash` — ainda). Sessões antigas do mesmo arquivo
ficam em `awaiting_resolve` até a TTL de 24h ou até serem descartadas
manualmente.

### Recuperação em caso de erro

- **Browser fechado no meio da resolução**: a sessão permanece no
  servidor por até 24h. Basta abrir `/imports/templates`, ativar o
  modo interativo, e — isso ainda é um TODO do frontend para uma
  versão futura — carregar o `session_id` anterior. Por ora, reanalise.
- **Servidor reiniciou**: sessões sobrevivem (ficam no Postgres).
- **Erro no commit**: a sessão fica em `error` com o motivo. Nenhuma
  linha foi importada (rollback). Você pode descartar e recomeçar, ou
  — se for algo que dê para editar na própria sessão — clicar em
  "Importar" de novo depois de resolver as pendências adicionais que
  a re-detecção surfaceou.

### Limitações conhecidas (v1 do modo interativo)

- Sem deep-link de sessão na URL ainda; fechar o navegador perde o
  contexto visual (a sessão persiste no servidor, mas a UI precisa ser
  re-estabelecida manualmente).
- Tipos de pendência não previstos caem no cartão genérico (apenas
  "Abortar").
- Mapeamento de FK requer que o operador saiba o ID numérico do
  registro-alvo — ainda não temos um picker com busca aqui. O cartão
  oferece um seletor pré-preenchido quando o detector surfaceia
  candidatos (para `fk_ambiguous`, por exemplo).

---

## 11.10e Modo interativo (v2) — ETL

Versão interativa do pipeline ETL documentado em 11.3 – 11.9. Mantém
a mesma semântica de transformação + substituição + validação, mas
**quebra o `execute` em duas fases** — `analyze` cria uma sessão no
servidor com o plano calculado; `commit` grava. Entre as duas, o
operador pode:

- ver **como as linhas foram agrupadas** por `erp_id` (para rotas com
  `auto_create_journal_entries` habilitado, uma `Transaction` agrega
  N `JournalEntry`s — ver 11.10c.2);
- revisar **cada substituição aplicada** como `campo: antigo → novo`
  (antes de gravar);
- resolver pendências (conta não mapeada, data inválida, coluna
  esperada ausente, conflito de `erp_id`, etc.) — inclusive criando
  `SubstitutionRule`s automaticamente a partir dos mapeamentos que
  fizer na tela.

### Ativação

Tela: `/imports` (aba **Importação ETL**) · botão **Modo interativo
(v2)** no topo.

Parâmetros adicionais que só existem no modo v2:

- `transformation_rule_id` (obrigatório) — qual regra de transformação
  aplicar. O link "Ver regras" leva à página `/imports/etl-rules`
  onde você pode copiar o ID.
- `auto_create_journal_entries` (opcional) — JSON idêntico ao aceito
  pelo endpoint legado `/api/core/etl/execute/`. Deixe em branco para
  importar sem contra-partida automática.

Exemplo mínimo do JSON:

```json
{
  "enabled": true,
  "bank_account_field": "bank_account_id",
  "opposing_account_field": "account_path"
}
```

### Fluxo de tela

```
┌────────────────────────────────────────────────────────────────┐
│ Modo: ( Clássico )  ( ✨ Modo interativo (v2) )                │
├────────────────────────────────────────────────────────────────┤
│ [file input]                                                   │
│ Regra de transformação:                                        │
│  ( Extrato BB C/C — Movimentos → Transaction   #12       ▼ )   │
│  ┌─ #12 · Extrato BB C/C ──────────────────────── dup: update ┐│
│  │ Aba origem: Movimentos  Modelo alvo: Transaction           ││
│  │ Mapeamentos: [Data → date] [Valor → amount] [Desc → desc…] ││
│  └─────────────────────────────────────────────────────────────┘│
│ Row limit: [ 0 ]                                               │
│ auto_create_journal_entries (JSON, opcional): [...]            │
│ [ Analisar ]                                                   │
└────────────────────────────────────────────────────────────────┘
    │
    ▼  (sessão criada)
┌────────────────────────────────────────────────────────────────┐
│ ▾ Grupos de erp_id · 3 grupos · 1 com linhas múltiplas         │
│   ▸ OMIE-NF-123    5 linhas   [GRUPO]   Será 1 Tx + N JEs      │
│   ▸ OMIE-NF-124    1 linha    [OK]      Transaction simples    │
│   ▸ (sem erp_id)   2 linhas   [OK]      ...                    │
│                                                                │
│ ⚠ Existem problemas que precisam ser resolvidos…               │
│                                          [ Importar ] (off)   │
│                                                                │
│ ℹ Substituições aplicadas                                      │
│   [account_path: "Aluguel" → "Despesas > Aluguel"]             │
│                                                                │
│ ⚠ Parâmetros ausentes (1) — ETL                                │
│   ┌────────────────────────────────────────────────────────┐   │
│   │ Coluna esperada ``bank_account_id`` não está em        │   │
│   │ Transaction. Ajuste o mapeamento da regra ou desabilite│   │
│   │ auto_create_journal_entries.                           │   │
│   │ [ Editar regra ]  [ Abortar ]                          │   │
│   └────────────────────────────────────────────────────────┘   │
│                                                                │
│ ⚠ Referências não mapeadas (2)                                 │
│   ... (mesmos cartões de 11.10d)                               │
└────────────────────────────────────────────────────────────────┘
```

### Pendências esperadas apenas no ETL

Além de todos os tipos descritos em 11.10d
(`erp_id_conflict`, `unmatched_reference`, `fk_ambiguous`,
`bad_date_format`, `negative_amount`), o modo ETL também detecta:

**`missing_etl_parameter`** — a regra de transformação (ou a config
em `auto_create_journal_entries`) espera uma coluna nas linhas
transformadas, mas ela não existe. Por exemplo: o JSON diz
`"bank_account_field": "bank_account_id"` mas nenhuma linha expõe
`bank_account_id`. Causa comum: o `column_mappings` da regra não
produz essa coluna a partir do arquivo fonte.

Ação disponível: **Editar regra** (deep-link para o editor) +
**Abortar**. Não há fix inline — corrija a regra e reimporte.

### Panel "Grupos de `erp_id`"

Uma seção exclusiva do modo ETL, surfaceada acima da lista de
pendências. Lista cada `erp_id` distinto em
`transformed_data.Transaction`:

| Status   | Significado                                           |
|----------|-------------------------------------------------------|
| OK       | 1 linha, sem conflito. Vira 1 `Transaction`.          |
| GRUPO    | N>1 linhas, sem conflito. Vira 1 `Transaction` + N `JournalEntry`s (perna agregada no banco, §11.10c.2). |
| CONFLITO | Linhas do mesmo `erp_id` divergem em campos-chave. Há um cartão `erp_id_conflict` abaixo esperando resolução. |

Cada linha da tabela expande para mostrar as linhas transformadas
cruas (JSON compacto) — útil para confirmar o que o pipeline produziu
antes de gravar.

**Observação importante:** no modo ETL o agrupamento acontece sobre
as linhas **pós-substituição/transformação**, não sobre o arquivo
original. Substituições de `erp_id` (raras, mas possíveis) já estão
aplicadas quando os grupos são montados.

### Panel "Substituições aplicadas"

Populado a partir de `session.substitutions_applied` — cada
substituição que o `ETLPipelineService` aplicou aparece como um
badge `campo: valor antigo → valor novo`. Use isto para confirmar
que o pipeline reescreveu os campos como esperado antes de commitar.

Exemplo comum: `account_path: "Aluguel" → "Despesas > Aluguel"` (uma
regra de substituição existente canonicalizou o caminho da conta).

### Passo a passo

**1. Ative o modo interativo.**

**2. Informe `transformation_rule_id`** e (opcional)
`auto_create_journal_entries`. Clique **Analisar**.

**3. Revise o painel "Grupos de `erp_id`"** — confirme se as linhas
agruparam como você esperava. Se um grupo não deveria existir (dois
boletos diferentes com o mesmo `erp_id` por engano na planilha),
corrija a fonte e reimporte; o modo interativo não tem ação para
"dividir um grupo em dois".

**4. Revise "Substituições aplicadas"** — todas as substituições
feitas pelo engine estão listadas. Se alguma não fizer sentido,
ajuste a `SubstitutionRule` correspondente em
`/imports/substitutions` e reimporte.

**5. Resolva pendências** (igual ao §11.10d) — cada cartão oferece
as ações que o detector declarou em `proposed_actions`.

**6. Clique Importar.** O backend roda `ETLPipelineService.execute`
com `commit=True` usando os mesmos bytes do arquivo + a config que
você passou, materializa qualquer `SubstitutionRule` que você marcou
em "criar regra", e grava tudo dentro de uma transação atômica.

### Diferenças em relação ao ETL clássico

| | Clássico (v1)              | Interativo (v2)                           |
|--------------------|-----------------------------|-------------------------------------------|
| Passos             | Preview → Execute          | Analyze → (Resolve)* → Commit             |
| Estado             | Sem persistência intermediária | Sessão no servidor, TTL 24h            |
| Substituições      | Só listadas se falharem    | Listadas todas, com `antigo → novo`       |
| Referências não encontradas | Erro por linha, operator corrige planilha | Cartão na tela, mapeia para registro existente + cria regra em um clique |
| Linhas com mesmo `erp_id` | Agrupa automaticamente (11.10c.2) — sem validação extra | Igual, mas com visualização + detecção de conflitos de campos |
| Parâmetros faltantes da config ETL | Silenciosamente ignorados (lançamento sai errado) | Bloqueia o commit com `missing_etl_parameter` |
| Auditoria de regras criadas | N/A (regras só criadas manualmente) | `SubstitutionRule.source="import_session"` + `source_session` FK |

### Painel "Prévia da importação"

Acima dos diagnósticos, o v2 mostra uma tabela "Prévia da importação"
com o que o `commit` vai escrever:

| Coluna     | Significado                                                      |
|------------|------------------------------------------------------------------|
| Criar      | Quantas linhas novas cada modelo receberia.                      |
| Atualizar  | Quantas linhas existentes seriam atualizadas (lookup por `erp_id`). |
| Falharia   | Quantas linhas estão marcadas para falhar no commit (erro já surfaceado como pendência acima). |

Os valores vêm de um dry-run do pipeline de importação
(`commit=False`):

- **Modo ETL:** sempre roda — `ETLPipelineService.execute(commit=False)`
  já acontece na análise; as contagens são passadas adiante.
- **Modo template:** roda automaticamente quando o total de linhas
  do arquivo é ≤ 5000. Acima disso o passo é pulado (custaria
  reescrever + rollback de milhares de linhas só pra contar) e o
  painel fica oculto. O operador ainda vê o total por aba em
  "Pronto para importar" e a lista de pendências.

Se uma linha estiver na coluna "Falharia", há uma pendência
correspondente no painel de diagnósticos que você pode resolver
antes de commitar.

### Limitações conhecidas (v1 do modo interativo)

Além das listadas em §11.10d:

- `auto_create_journal_entries` é um campo de texto livre (JSON). Um
  formulário guiado (campo a campo) fica para iteração futura.
- O painel "Grupos de `erp_id`" não oferece ação para dividir um grupo
  em dois — se dois boletos realmente têm o mesmo `erp_id` por engano
  do ERP, corrija na fonte e reimporte.
- O seletor de regras mostra as regras ativas (`is_active != false`).
  Para gerenciar as regras em si (criar, editar, desativar) ainda
  não há uma tela dedicada — use o endpoint REST
  `/api/core/etl/transformation-rules/` diretamente (GET/POST/PATCH/DELETE).

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
| `*_erp_id` não resolve FK | Confirme que o registro relacionado existe e tem o `erp_id` preenchido |
| `__erp_id` não encontra registro | Confirme que o modelo tem o campo `erp_id` e que o valor corresponde |
| Duplicatas | Use `__erp_id` ou `__row_id` para atualizar registros existentes em vez de criar novos |
| `erp_id` compartilhado em linhas com campos divergentes | Veja 11.10c — o sistema rejeita com o campo conflitante no erro. Corrija a planilha ou use `erp_id`s distintos. |
| Modo 2 criou apenas 1 Tx quando eu esperava várias | Verifique se o `erp_id` está duplicado entre linhas — o agrupamento é intencional (ver 11.10c.2) |
| Modo 2 — erro "grupo exige 1 conta bancária" | Duas linhas com o mesmo `erp_id` indicaram `bank_account_id` diferentes. Um erp_id = um movimento bancário. Separe em dois `erp_id`s. |
| Re-importação apagou meus lançamentos customizados | No Modo 2, re-importar com o mesmo `erp_id` regenera os filhos. Edite a planilha de origem em vez do banco, ou use `erp_duplicate_behavior: "error"`. |
| Timeout | Para arquivos grandes, `CELERY_TASK_TIME_LIMIT` (default 30min) pode ser excedido — aumente via env var, ou divida o arquivo. |
| Sessão parada em `analyzing` / `committing` por muito tempo | Worker pode ter morrido. Espere ~5 min — o reaper `imports_v2.reap_stale_sessions` flipa para `error`. Ou descarte a sessão manualmente. |
| Importação anormalmente lenta (minutos para poucos milhares de linhas) | Se a versão do backend for anterior a 6.z-f, o `LookupCache` pode não estar carregado. Atualize o backend. |

---

*Anterior: [10 — Estoque](10-estoque.md) · Próximo: [12 — Integrações ERP](12-integracoes-erp.md)*

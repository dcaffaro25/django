# 06 — Conciliação Bancária

A conciliação bancária é um dos módulos mais sofisticados da plataforma Nord. Ele combina regras configuráveis, inteligência artificial (embeddings semânticos) e um pipeline de múltiplos estágios para automatizar o cruzamento entre extratos bancários e lançamentos contábeis.

---

## 6.1 Conceitos Fundamentais

### O que é Conciliação Bancária?

Conciliação bancária é o processo de cruzar:
- **Transações bancárias** (extrato do banco) com
- **Lançamentos contábeis** (journal entries) no sistema

O objetivo é garantir que cada movimentação bancária tenha um correspondente na contabilidade, identificando:
- Movimentações conciliadas (match encontrado)
- Movimentações pendentes (sem match)
- Divergências (valores ou datas inconsistentes)

### Fluxo Geral

```
┌─────────────────┐     ┌───────────────────┐     ┌─────────────────┐
│ Extrato Bancário│     │   Pipeline de     │     │  Conciliações   │
│ (Bank Trans.)   │────►│   Conciliação     │────►│  (Reconcil.)    │
└─────────────────┘     │                   │     └─────────────────┘
                        │ 1. Filtros        │
┌─────────────────┐     │ 2. Matching       │     ┌─────────────────┐
│ Lançamentos     │────►│ 3. Scoring        │────►│  Sugestões      │
│ (Journal Entries)│     │ 4. Embeddings     │     │  (Suggestions)  │
└─────────────────┘     └───────────────────┘     └─────────────────┘
```

---

## 6.2 Configuração Inicial

### 1. Criar Configuração de Conciliação

Cada empresa precisa de uma configuração de conciliação:

```bash
POST /acme/api/reconciliation_configs/
{
  "name": "Conciliação Padrão",
  "company": 1,
  "config": {
    "date_tolerance_days": 3,
    "amount_tolerance_percent": 0.01,
    "min_confidence_score": 0.7,
    "use_embeddings": true
  }
}
```

**Parâmetros da config:**

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `date_tolerance_days` | int | Diferença máxima em dias entre as datas |
| `amount_tolerance_percent` | float | Tolerância percentual no valor (0.01 = 1%) |
| `min_confidence_score` | float | Score mínimo para considerar uma sugestão válida |
| `use_embeddings` | bool | Usar embeddings semânticos para matching |

### 2. Criar Pipeline de Conciliação

O pipeline define os estágios de processamento:

```bash
POST /acme/api/reconciliation-pipelines/
{
  "name": "Pipeline Padrão",
  "company": 1,
  "config": 1,
  "stages": [
    {"name": "Exact Match", "order": 1, "type": "exact"},
    {"name": "Fuzzy Match", "order": 2, "type": "fuzzy"},
    {"name": "Embedding Match", "order": 3, "type": "embedding"}
  ]
}
```

### 3. Criar Regras de Conciliação (Opcional)

Regras permitem personalizar o matching para padrões recorrentes:

```bash
POST /acme/api/reconciliation-rules/
{
  "name": "PIX Recebimento",
  "company": 1,
  "bank_description_pattern": "PIX\\s+RECEB.*",
  "journal_description_pattern": "Recebimento.*cliente",
  "priority": 10,
  "is_active": true
}
```

---

## 6.3 Executando a Conciliação

### Iniciar uma Tarefa de Conciliação

```bash
POST /acme/api/reconciliation-tasks/
{
  "config": 1,
  "pipeline": 1,
  "date_from": "2026-03-01",
  "date_to": "2026-03-31"
}
```

A tarefa é processada em background via Celery. A resposta inclui o `task_id` para acompanhamento.

### Acompanhar Status

```bash
# Via endpoint de tarefas
GET /api/tasks/{task_id}/

# Via reconciliation tasks
GET /acme/api/reconciliation-tasks/{id}/
```

**Estados possíveis:**

| Estado | Descrição |
|--------|-----------|
| `pending` | Aguardando processamento |
| `running` | Em execução |
| `completed` | Finalizado com sucesso |
| `failed` | Falhou |
| `cancelled` | Cancelado |

### Cancelar uma Tarefa

```bash
POST /api/tasks/{task_id}/stop/
```

---

## 6.4 Sugestões de Conciliação

Após a execução do pipeline, o sistema gera **sugestões** de correspondência.

### Listar Sugestões

```bash
GET /acme/api/bank_transactions/suggest_matches/
```

### Estrutura de uma Sugestão

```json
{
  "bank_transaction_ids": [101],
  "journal_entry_ids": [205, 206],
  "confidence_score": 0.92,
  "match_type": "fuzzy",
  "payload": {
    "bank_amount": 5000.00,
    "journal_total": 5000.00,
    "date_diff_days": 1,
    "description_similarity": 0.85
  }
}
```

### Aceitar/Rejeitar Sugestões

Para aceitar uma sugestão e criar a conciliação completa:

```bash
POST /acme/api/reconciliation/
{
  "journal_entries": [205, 206],
  "bank_transactions": [101],
  "status": "matched"
}
```

### Conciliações Parciais (Status `open`)

Nem sempre todas as informações estão disponíveis de uma vez. Por exemplo, você identificou que uma transação bancária de R$ 10.000 corresponde a vários lançamentos contábeis, mas ainda não encontrou todos. Nesses casos, crie uma **conciliação parcial** com status `open`:

```bash
POST /acme/api/reconciliation/
{
  "journal_entries": [205],
  "bank_transactions": [101],
  "status": "open"
}
```

**Status `open` indica:**
- A conciliação foi criada manualmente mas **ainda não está fechada**
- Novos lançamentos ou transações bancárias podem ser adicionados depois
- No dashboard, aparece como "parcial" e não como "conciliada"

**Fechando uma conciliação parcial:**

Quando todos os registros estiverem vinculados, atualize o status:

```bash
PATCH /acme/api/reconciliation/{id}/
{
  "status": "matched",
  "journal_entries": [205, 206, 207],
  "bank_transactions": [101]
}
```

### Status de uma Conciliação

| Status | Descrição |
|--------|-----------|
| `pending` | Criada automaticamente, aguardando revisão |
| `open` | **Parcial** — vinculação manual em andamento, ainda não fechada |
| `matched` | Conciliada e confirmada |
| `unmatched` | Marcada como sem correspondência |
| `review` | Aguardando revisão manual |
| `approved` | Aprovada por supervisor |

### Exemplo Completo: Conciliação Parcial de Pagamento Parcelado

**Cenário:** O banco mostra um depósito de R$ 30.000, mas os lançamentos contábeis serão lançados ao longo do mês (3 parcelas de R$ 10.000).

**Passo 1 — Criar conciliação parcial com a 1ª parcela:**
```bash
POST /acme/api/reconciliation/
{
  "journal_entries": [301],
  "bank_transactions": [500],
  "status": "open"
}
# Resposta: {"id": 42, "status": "open", ...}
```

**Passo 2 — Quando a 2ª parcela for lançada, adicionar à conciliação:**
```bash
PATCH /acme/api/reconciliation/42/
{
  "journal_entries": [301, 302],
  "status": "open"
}
```

**Passo 3 — Com a 3ª parcela, fechar a conciliação:**
```bash
PATCH /acme/api/reconciliation/42/
{
  "journal_entries": [301, 302, 303],
  "status": "matched"
}
```

> **Dica:** Use o endpoint `/acme/api/reconciliation/summaries/` para ver o resumo de conciliações por status, incluindo quantas estão com status `open` (parcial).

---

## 6.5 Tipos de Matching

### 1. Match Exato (1:1)

Uma transação bancária corresponde exatamente a um lançamento contábil:
- Mesmo valor (dentro da tolerância)
- Mesma data (dentro da tolerância)
- Descrição correspondente

### 2. Match Muitos-para-Um (N:1)

Múltiplos lançamentos contábeis somam para igualar uma transação bancária:
- A soma dos lançamentos = valor da transação bancária
- Comum em pagamentos agrupados

### 3. Match Um-para-Muitos (1:N)

Uma transação bancária é dividida entre múltiplas conciliações:
- Comum quando o banco agrupa várias operações em um único lançamento

### 4. Match via Embeddings

Quando o matching por regras não encontra correspondência, o sistema usa **embeddings semânticos**:
- Converte descrições em vetores numéricos
- Calcula similaridade cosseno entre transações bancárias e lançamentos
- Apresenta as correspondências mais prováveis

---

## 6.6 Dashboard de Conciliação

### Visão Geral (Não Conciliadas)

```bash
GET /acme/reconciliation-dashboard/
```

Retorna:
- Total de transações bancárias não conciliadas
- Total de lançamentos contábeis não conciliados
- Estatísticas por conta bancária
- Resumo por período

### Relatório de Não Conciliadas

```bash
GET /acme/api/reconciliation/export-unreconciled-report/
```

Exporta relatório detalhado das transações pendentes.

### Sumários

```bash
GET /acme/api/reconciliation/summaries/
```

---

## 6.7 Regras de Conciliação

### Estrutura de uma Regra

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | string | Nome descritivo |
| `bank_description_pattern` | regex | Padrão para descrição do extrato |
| `journal_description_pattern` | regex | Padrão para descrição do lançamento |
| `priority` | integer | Prioridade (maior = aplica primeiro) |
| `is_active` | boolean | Regra ativa |

### Exemplos de Regras Comuns

**Transferências PIX:**
```json
{
  "name": "PIX Transferência",
  "bank_description_pattern": "PIX\\s+(ENVIADO|RECEBIDO).*",
  "journal_description_pattern": "PIX.*",
  "priority": 10
}
```

**Débito Automático de Conta de Luz:**
```json
{
  "name": "Débito Energia",
  "bank_description_pattern": "DEB\\s+AUTO.*ELETRO.*",
  "journal_description_pattern": "Energia\\s+Elétrica.*",
  "priority": 8
}
```

**Boletos:**
```json
{
  "name": "Pagamento Boleto",
  "bank_description_pattern": "PAG\\s+BOLETO.*",
  "journal_description_pattern": "Fornecedor.*boleto.*",
  "priority": 5
}
```

### Validar e Propor Regras

```bash
# Propor novas regras baseadas no histórico
POST /acme/api/reconciliation-rules/propose/

# Validar uma regra antes de criar
POST /acme/api/reconciliation-rules/validate/
{
  "bank_description_pattern": "PIX.*",
  "journal_description_pattern": "Transferência.*"
}
```

---

## 6.8 Métricas de Conciliação

### Recalcular Métricas

```bash
POST /acme/api/reconciliation-metrics/recalculate/
```

### Métricas por Transação

```bash
GET /acme/api/reconciliation-metrics/transaction/{id}/
```

### Métricas por Lançamento

```bash
GET /acme/api/reconciliation-metrics/journal-entry/{id}/
```

---

## 6.9 Tags de Conciliação

Tags são rótulos de texto livre que podem ser atribuídos a **lançamentos contábeis** e **transações bancárias** para organizar o processo de conciliação. São especialmente úteis para:

- Agrupar registros que pertencem a uma mesma operação
- Marcar itens para revisão futura
- Classificar registros por tipo de operação ou fornecedor
- Facilitar conciliações parciais, agrupando os registros envolvidos

### Atribuir Tags em Lote

O endpoint de tags permite atribuir a mesma tag (ou tags diferentes) a múltiplos registros de uma vez:

```bash
POST /acme/api/reconciliation-record-tags/
{
  "tags": [
    {"record_type": "bank_transaction", "record_id": 101, "tag": "parcela-mar-2026"},
    {"record_type": "bank_transaction", "record_id": 102, "tag": "parcela-mar-2026"},
    {"record_type": "journal_entry", "record_id": 205, "tag": "parcela-mar-2026"},
    {"record_type": "journal_entry", "record_id": 206, "tag": "parcela-mar-2026"}
  ]
}
```

**Resposta:**

```json
{
  "updated": 4
}
```

### Alterar ou Remover Tags

Para alterar a tag, basta enviar novamente o mesmo `record_type`/`record_id` com a nova tag. Para remover, envie uma string vazia:

```bash
POST /acme/api/reconciliation-record-tags/
{
  "tags": [
    {"record_type": "bank_transaction", "record_id": 101, "tag": ""},
    {"record_type": "journal_entry", "record_id": 205, "tag": "revisado"}
  ]
}
```

### Filtrar Registros por Tag

Depois de atribuir tags, filtre lançamentos e transações bancárias para ver todos de um mesmo grupo:

```bash
# Todos os lançamentos contábeis com a tag "parcela-mar-2026"
GET /acme/api/journal_entries/?tag=parcela-mar-2026

# Todas as transações bancárias com a tag "parcela-mar-2026"
GET /acme/api/bank_transactions/?tag=parcela-mar-2026
```

### Exemplo Prático: Agrupando Registros para Conciliação

**Cenário:** Você tem 3 boletos no extrato bancário e 5 lançamentos contábeis que correspondem à mesma operação de pagamento de fornecedores.

**Passo 1 — Atribuir a mesma tag a todos os registros:**
```bash
POST /acme/api/reconciliation-record-tags/
{
  "tags": [
    {"record_type": "bank_transaction", "record_id": 101, "tag": "pgto-fornecedores-mar"},
    {"record_type": "bank_transaction", "record_id": 102, "tag": "pgto-fornecedores-mar"},
    {"record_type": "bank_transaction", "record_id": 103, "tag": "pgto-fornecedores-mar"},
    {"record_type": "journal_entry", "record_id": 301, "tag": "pgto-fornecedores-mar"},
    {"record_type": "journal_entry", "record_id": 302, "tag": "pgto-fornecedores-mar"},
    {"record_type": "journal_entry", "record_id": 303, "tag": "pgto-fornecedores-mar"},
    {"record_type": "journal_entry", "record_id": 304, "tag": "pgto-fornecedores-mar"},
    {"record_type": "journal_entry", "record_id": 305, "tag": "pgto-fornecedores-mar"}
  ]
}
```

**Passo 2 — Verificar o grupo completo:**
```bash
GET /acme/api/bank_transactions/?tag=pgto-fornecedores-mar
GET /acme/api/journal_entries/?tag=pgto-fornecedores-mar
```

**Passo 3 — Criar a conciliação (parcial ou completa):**
```bash
POST /acme/api/reconciliation/
{
  "bank_transactions": [101, 102, 103],
  "journal_entries": [301, 302, 303, 304, 305],
  "status": "matched"
}
```

---

## 6.10 Fluxo Completo — Exemplo Prático

### Cenário: Conciliar março de 2026

**Passo 1 — Importar extrato bancário:**
```bash
# Via ETL (planilha Excel)
POST /acme/api/core/etl/execute/
# ou via API direta
POST /acme/api/bank_transactions/bulk_create/
```

**Passo 2 — Verificar configuração:**
```bash
GET /acme/api/reconciliation_configs/
```

**Passo 3 — Executar conciliação:**
```bash
POST /acme/api/reconciliation-tasks/
{
  "config": 1,
  "pipeline": 1,
  "date_from": "2026-03-01",
  "date_to": "2026-03-31"
}
```

**Passo 4 — Acompanhar progresso:**
```bash
GET /api/tasks/{task_id}/
```

**Passo 5 — Revisar sugestões:**
```bash
GET /acme/api/bank_transactions/suggest_matches/
```

**Passo 6 — Aceitar matches confiáveis (conciliação completa):**
```bash
POST /acme/api/reconciliation/
{"journal_entries": [205], "bank_transactions": [101], "status": "matched"}
```

**Passo 6b — Para matches parciais, criar conciliação aberta:**
```bash
POST /acme/api/reconciliation/
{"journal_entries": [210], "bank_transactions": [105], "status": "open"}
```

**Passo 7 — Agrupar pendências com tags:**
```bash
POST /acme/api/reconciliation-record-tags/
{
  "tags": [
    {"record_type": "bank_transaction", "record_id": 106, "tag": "investig-mar"},
    {"record_type": "journal_entry", "record_id": 215, "tag": "investig-mar"}
  ]
}
```

**Passo 8 — Verificar pendências:**
```bash
GET /acme/reconciliation-dashboard/
```

**Passo 9 — Comparar saldos diários banco vs livro:**
```bash
GET /acme/api/bank-book-daily-balances/?date_from=2026-03-01&date_to=2026-03-31
```

---

## 6.11 Dicas Avançadas

### Performance

- Execute conciliações para **períodos menores** (mensal) para melhor performance
- Use `max_suggestions` no pipeline para limitar resultados e acelerar o processamento
- Mantenha os embeddings atualizados com backfill periódico

### Qualidade

- Crie regras específicas para padrões recorrentes do seu banco
- Ajuste `date_tolerance_days` e `amount_tolerance_percent` conforme seu fluxo
- Revise sugestões com score abaixo de 0.8 manualmente
- Use tags para marcar itens para revisão futura

### Troubleshooting

| Problema | Solução |
|----------|---------|
| Poucas sugestões | Reduza `min_confidence_score`, aumente tolerâncias |
| Muitas sugestões falsas | Aumente `min_confidence_score`, crie regras mais específicas |
| Tarefa demora muito | Reduza o período, verifique se Celery/Redis estão saudáveis |
| Embeddings não funcionam | Execute backfill, verifique saúde (`/embeddings/health/`) |

---

*Anterior: [05 — Contabilidade](05-contabilidade.md) · Próximo: [07 — Demonstrações Financeiras](07-demonstracoes-financeiras.md)*

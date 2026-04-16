# 13 — Regras de Automação

A plataforma Nord oferece dois sistemas de regras que automatizam transformações e ações: **Regras de Substituição** (de-para) e **Regras de Integração** (triggers automáticos).

---

## 13.1 Regras de Substituição (SubstitutionRule)

### O que São?

Regras de substituição funcionam como uma **tabela de-para**: quando um valor é encontrado em um campo durante a importação de dados, ele é automaticamente substituído por outro valor.

### Quando São Usadas?

- Durante importações ETL (planilhas Excel)
- Na normalização de dados de ERPs externos
- Na padronização de nomes de contas, centros de custo, parceiros, etc.

### Estrutura da Regra

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `company` | FK Company | Empresa dona da regra |
| `model_name` | string | Modelo alvo (ex: `Transaction`, `JournalEntry`) |
| `field_name` | string | Campo alvo (ex: `description`, `account`, `cost_center`) |
| `match_type` | choice | Tipo de correspondência |
| `match_value` | string | Valor a ser encontrado |
| `substitution_value` | string | Valor de substituição |
| `filter_conditions` | JSON | Condições adicionais para aplicar a regra (opcional) |

### Tipos de Correspondência

| `match_type` | Descrição | Exemplo |
|--------------|-----------|---------|
| `exact` | Correspondência exata | `"CC-001"` → `"TI"` |
| `contains` | Contém o texto | `"energia"` em `"Pag energia elétrica"` |
| `startswith` | Começa com | `"PIX"` em `"PIX RECEBIDO 12345"` |
| `endswith` | Termina com | `".gov.br"` em `"email@receita.gov.br"` |
| `regex` | Expressão regular | `"NF\s*\d+"` em `"NF 12345"` |
| `iexact` | Exata (case-insensitive) | `"abc"` = `"ABC"` |
| `icontains` | Contém (case-insensitive) | `"ENERGIA"` em `"pag energia"` |

### Exemplos Práticos

#### Normalizar Nomes de Conta

```bash
POST /acme/api/core/substitution-rules/
{
  "model_name": "JournalEntry",
  "field_name": "account",
  "match_type": "exact",
  "match_value": "1.1.01.001",
  "substitution_value": "Banco do Brasil C/C Principal"
}
```

#### Classificar Transações por Descrição

```bash
POST /acme/api/core/substitution-rules/
{
  "model_name": "Transaction",
  "field_name": "description",
  "match_type": "regex",
  "match_value": "PIX\\s+RECEB.*",
  "substitution_value": "Recebimento via PIX",
  "filter_conditions": {"amount__gt": 0}
}
```

#### Mapear Centro de Custo do ERP

```bash
POST /acme/api/core/substitution-rules/
{
  "model_name": "Transaction",
  "field_name": "cost_center",
  "match_type": "startswith",
  "match_value": "DEPTO-",
  "substitution_value": "Departamento Administrativo"
}
```

### Condições de Filtro

O campo `filter_conditions` permite aplicar a regra apenas quando condições adicionais são atendidas:

```json
{
  "filter_conditions": {
    "amount__gt": 1000,
    "entity__name": "Filial SP",
    "date__gte": "2026-01-01"
  }
}
```

**Operadores suportados:**

| Operador | Significado |
|----------|-------------|
| `__gt` | Maior que |
| `__gte` | Maior ou igual |
| `__lt` | Menor que |
| `__lte` | Menor ou igual |
| `__exact` | Igual (padrão) |
| `__contains` | Contém |
| `__startswith` | Começa com |

### Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/api/core/substitution-rules/` | Listar regras |
| `POST` | `/api/core/substitution-rules/` | Criar regra |
| `PUT/PATCH` | `/api/core/substitution-rules/{id}/` | Atualizar |
| `DELETE` | `/api/core/substitution-rules/{id}/` | Excluir |

### Validar uma Regra

Antes de criar, teste se a regra funciona:

```bash
POST /api/core/validate-rule/
{
  "match_type": "regex",
  "match_value": "PIX\\s+RECEB.*",
  "test_input": "PIX RECEBIDO DE JOAO SILVA"
}
```

### Testar uma Regra

Execute a regra contra dados de teste:

```bash
POST /api/core/test-rule/
{
  "rule_id": 5,
  "test_data": [
    {"description": "PIX RECEBIDO DE MARIA", "amount": 500},
    {"description": "TED ENVIADA PARA JOSE", "amount": -1000}
  ]
}
```

---

## 13.2 Regras de Integração (IntegrationRule)

### O que São?

Regras de integração são **triggers automáticos** que executam ações quando eventos específicos ocorrem no sistema. Funcionam como webhooks internos.

### Estrutura da Regra

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `company` | FK Company | Empresa |
| `name` | string | Nome descritivo |
| `trigger_event` | string | Evento que dispara a regra |
| `rule` | JSON | Lógica da regra (condições e ações) |
| `filter_conditions` | JSON | Filtros adicionais |
| `use_celery` | boolean | Executar em background via Celery |
| `is_active` | boolean | Regra ativa |

### Eventos de Trigger

| Evento | Descrição |
|--------|-----------|
| `transaction.created` | Nova transação criada |
| `transaction.posted` | Transação postada |
| `journal_entry.created` | Novo lançamento contábil |
| `bank_transaction.created` | Nova transação bancária |
| `reconciliation.created` | Nova conciliação |
| `nfe.imported` | NF-e importada |
| `etl.completed` | Importação ETL finalizada |

### Exemplo: Auto-classificar Transações Importadas

```bash
POST /acme/api/core/integration-rules/
{
  "name": "Auto-classificar PIX",
  "trigger_event": "transaction.created",
  "rule": {
    "conditions": {
      "description__contains": "PIX"
    },
    "actions": [
      {
        "type": "set_field",
        "field": "tag",
        "value": "pix"
      }
    ]
  },
  "is_active": true,
  "use_celery": false
}
```

### Exemplo: Notificar quando Valor Alto

```bash
POST /acme/api/core/integration-rules/
{
  "name": "Alerta Transação Alta",
  "trigger_event": "transaction.created",
  "rule": {
    "conditions": {
      "amount__gt": 100000
    },
    "actions": [
      {
        "type": "log",
        "message": "Transação de alto valor detectada"
      }
    ]
  },
  "is_active": true,
  "use_celery": true
}
```

### Logs de Execução

Cada execução de regra gera um log:

```bash
# As logs estão acessíveis via Django Admin
# Admin → Multitenancy → Integration Rule Logs
```

O log registra:
- Payload que disparou a regra
- Resultado da execução
- Sucesso ou falha

### Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/api/core/integration-rules/` | Listar regras |
| `POST` | `/api/core/integration-rules/` | Criar regra |
| `PUT/PATCH` | `/api/core/integration-rules/{id}/` | Atualizar |
| `DELETE` | `/api/core/integration-rules/{id}/` | Excluir |

---

## 13.3 Combinando Regras com ETL

O fluxo mais poderoso combina os três sistemas:

```
┌──────────┐   ┌──────────────────┐   ┌──────────────────┐   ┌──────────┐
│ Planilha │──►│ Regras de        │──►│ Importação ETL   │──►│ Regras   │
│ Excel    │   │ Substituição     │   │ (persistência)   │   │ Integração│
│          │   │ (normalização)   │   │                  │   │ (trigger) │
└──────────┘   └──────────────────┘   └──────────────────┘   └──────────┘
```

1. O ETL lê a planilha
2. Regras de substituição normalizam nomes, códigos e categorias
3. Dados normalizados são importados no banco
4. Regras de integração disparam ações automáticas (classificação, alertas, etc.)

### Exemplo Prático

**Cenário:** Importar extrato bancário e auto-classificar.

**1. Regras de substituição para normalizar descrições:**
```bash
# "PIX RECEB" → "Recebimento PIX"
# "DEB AUTO" → "Débito Automático"  
# "TARIFA" → "Tarifa Bancária"
```

**2. Regra de transformação ETL para mapear colunas.**

**3. Regras de integração para classificar:**
```bash
# Se descrição contém "Tarifa" → tag = "tarifa_bancaria"
# Se valor > 50000 → gerar alerta
# Se descrição contém "Salário" → vincular a centro de custo "RH"
```

---

## 13.4 Boas Práticas

### Regras de Substituição

- **Comece com `exact`** — é o mais previsível e rápido
- **Use `regex` com cuidado** — teste sempre antes com `/validate-rule/`
- **Documente** o propósito de cada regra no admin (campo notas)
- **Ordene** regras específicas antes de genéricas (o sistema aplica na ordem encontrada)
- **Use filter_conditions** para regras que só devem aplicar em contextos específicos

### Regras de Integração

- **Use `use_celery: true`** para ações pesadas (evita atrasar a requisição original)
- **Monitore os logs** periodicamente para verificar falhas
- **Comece com regras simples** e vá adicionando complexidade gradualmente
- **Teste em ambiente de homologação** antes de ativar em produção

---

*Anterior: [12 — Integrações ERP](12-integracoes-erp.md) · Próximo: [14 — Recursos Avançados](14-recursos-avancados.md)*

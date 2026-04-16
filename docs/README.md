# Documentação — Plataforma Nord

## Estrutura da Documentação

```
docs/
├── manual/              ← Manual do Usuário (pt-BR)
│   ├── README.md            Índice principal
│   ├── 01-introducao.md     Visão geral da plataforma
│   ├── 02-primeiros-passos.md
│   ├── 03-admin-django.md   Guia do Django Admin
│   ├── 04-multitenancy-usuarios.md
│   ├── 05-contabilidade.md
│   ├── 06-conciliacao-bancaria.md
│   ├── 07-demonstracoes-financeiras.md
│   ├── 08-faturamento-nfe.md
│   ├── 09-rh-folha.md
│   ├── 10-estoque.md
│   ├── 11-etl-importacao.md
│   ├── 12-integracoes-erp.md
│   ├── 13-regras-automacao.md
│   ├── 14-recursos-avancados.md
│   └── 15-api-referencia.md
│
├── architecture/        ← Documentação técnica aprofundada
│   ├── RECONCILIATION.md
│   ├── TRANSACTION_RECONCILIATION_API.md
│   ├── RECONCILIATION_TASK_COMPATIBILITY.md
│   ├── FINANCIAL_STATEMENTS.md
│   ├── FINANCIAL_STATEMENT_FORMULAS.md
│   ├── FINANCIAL_STATEMENT_TESTING.md
│   ├── INCOME_STATEMENT_ENDPOINT_USAGE.md
│   ├── ETL_PIPELINE_DOCUMENTATION.md
│   ├── SUBSTITUTION_AND_INTEGRATION_RULES_DOCUMENTATION.md
│   ├── CORE_TASK_MANAGEMENT_README.md
│   ├── KNOWLEDGE_BASE_README.md
│   ├── KNOWLEDGE_BASE_API_EXAMPLES.md
│   ├── TEMPLATE_PREVIEW_GUIDE.md
│   └── TUTORIAL_IMPLEMENTATION.md
│
├── dev/                 ← Guias de desenvolvimento e deploy
│   ├── LOCAL_DEVELOPMENT.md
│   ├── README_DJANGO_SERVER.md
│   ├── RAILWAY_COMMANDS.md
│   ├── RAILWAY_ENV_VARIABLES.md
│   ├── RAILWAY_DELETE_TABLE_GUIDE.md
│   └── AI_ASSISTANT_RULES.md
│
├── inventory/           ← Documentação de estoque
│   ├── INVENTORY_MANUAL.md
│   └── INVENTORY_NF_WALKTHROUGH.md
│
├── erp-sync-job-manual.md   ← Manual de sync ERP
│
└── archive/             ← Documentos históricos e planos
    ├── plans/
    │   ├── ACCOUNT_BALANCE_HISTORY_PLAN.md
    │   ├── ADMIN_IMPROVEMENT_PLAN.md
    │   ├── RECONCILIATION_FINANCIAL_METRICS_PLAN.md
    │   └── KNOWLEDGE_BASE_REUSE_PLAN.md
    └── retool/
        ├── RETOOL_FRONTEND_EXPLORATION.md
        └── UI_UX_DOCUMENTATION.md
```

## Para Usuários

Comece pelo **[Manual do Usuário](manual/README.md)** — documentação completa em português (pt-BR) cobrindo:
- Primeiros passos e autenticação
- Django Admin
- Todos os módulos de negócio (contabilidade, conciliação, demonstrações financeiras, faturamento, RH, estoque)
- Integrações ERP e importação ETL
- Regras de automação
- Referência completa da API

## Para Desenvolvedores

- [Desenvolvimento Local](dev/LOCAL_DEVELOPMENT.md)
- [Deploy Railway](dev/RAILWAY_COMMANDS.md)
- [Variáveis de Ambiente](dev/RAILWAY_ENV_VARIABLES.md)
- Documentação técnica aprofundada em `architecture/`

## Para Integração (OpenClaw)

- [OPENCLAW_API_MANUAL.md](../OPENCLAW_API_MANUAL.md) — Manual para o agente AI

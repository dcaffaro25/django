# 15 — Referência da API

Catálogo completo de todos os endpoints disponíveis na plataforma Nord, organizados por módulo.

---

## 15.1 Convenções

| Aspecto | Descrição |
|---------|-----------|
| **Base URL** | `https://servidor.com/` |
| **Autenticação** | `Authorization: Token <token>` |
| **Content-Type** | `application/json` (exceto uploads: `multipart/form-data`) |
| **Tenant** | Prefixo `/{tenant}/` para endpoints com escopo de empresa |
| **Paginação** | `?page=N&page_size=M` (padrão: 100 itens) |
| **Ordenação** | `?ordering=campo` (prefixo `-` para decrescente) |
| **Busca** | `?search=termo` |
| **Formato de data** | `YYYY-MM-DD` |

### Códigos de Resposta

| Código | Significado |
|--------|-------------|
| `200` | Sucesso |
| `201` | Criado com sucesso |
| `204` | Excluído com sucesso |
| `400` | Dados inválidos (ver erros no body) |
| `401` | Não autenticado |
| `403` | Sem permissão |
| `404` | Não encontrado |
| `500` | Erro interno do servidor |

---

## 15.2 Autenticação e Sessão

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/login/` | Login (retorna token) |
| `POST` | `/logout/` | Logout (invalida token) |
| `POST` | `/change-password/` | Alterar senha própria |
| `POST` | `/reset-password/` | Solicitar reset de senha |
| `POST` | `/force-reset-password/` | Reset forçado (admin) |
| `POST` | `/api/token/` | Obter par JWT |
| `POST` | `/api/token/refresh/` | Renovar JWT |

---

## 15.3 Usuários e Empresas (Global)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/api/core/users/` | CRUD usuários |
| `POST` | `/api/core/users/create/` | Criar usuário |
| `GET/PUT/PATCH/DELETE` | `/api/core/users/{id}/` | Detalhe/editar/excluir |
| `GET/POST` | `/api/core/companies/` | CRUD empresas |
| `GET/PUT/PATCH/DELETE` | `/api/core/companies/{id}/` | Detalhe empresa |
| `GET` | `/api/core/companies/{id}/reconciliation-summary/` | Resumo de conciliação |
| `GET/POST` | `/api/core/currencies/` | CRUD moedas |

---

## 15.4 Contabilidade

### Contas (Accounts)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{t}/api/accounts/` | Listar/criar contas |
| `GET/PUT/PATCH/DELETE` | `/{t}/api/accounts/{id}/` | CRUD conta |
| `POST` | `/{t}/api/accounts/bulk_create/` | Criar em lote |
| `POST` | `/{t}/api/accounts/bulk_update/` | Atualizar em lote |
| `POST` | `/{t}/api/accounts/bulk_delete/` | Excluir em lote |

### Transações (Transactions)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{t}/api/transactions/` | Listar/criar |
| `GET/PUT/PATCH/DELETE` | `/{t}/api/transactions/{id}/` | CRUD |
| `POST` | `/{t}/transactions/{id}/post/` | Postar transação |
| `POST` | `/{t}/transactions/{id}/unpost/` | Despostar |
| `POST` | `/{t}/transactions/{id}/cancel/` | Cancelar |
| `POST` | `/{t}/transactions/{id}/create_balancing_entry/` | Criar lançamento de ajuste |
| `GET` | `/{t}/api/transactions/unmatched/` | Não conciliadas |
| `GET` | `/{t}/api/transactions/unbalanced/` | Desbalanceadas |
| `GET` | `/{t}/api/transactions/{id}/balance-status/` | Status de saldo |
| `GET` | `/{t}/api/transactions/{id}/validate-balance/` | Validar saldo |
| `POST` | `/{t}/api/transactions/bulk-validate-balance/` | Validar em lote |
| `GET` | `/{t}/api/transactions/summary-stats/` | Estatísticas |
| `POST` | `/{t}/api/transactions/bulk_create/` | Criar em lote |
| `POST` | `/{t}/api/transactions/bulk_update/` | Atualizar em lote |
| `POST` | `/{t}/api/transactions/bulk_delete/` | Excluir em lote |

**Filtros de Transação:** `nf_number`, `cliente_erp_id`, `due_date_from`, `due_date_to`, `search` (pesquisa em description, nf_number, cliente_erp_id, numero_boleto, cnpj)

### Lançamentos Contábeis (Journal Entries)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{t}/api/journal_entries/` | Listar/criar |
| `GET/PUT/PATCH/DELETE` | `/{t}/api/journal_entries/{id}/` | CRUD |
| `POST` | `/{t}/api/journal_entries/bulk_create/` | Criar em lote |
| `POST` | `/{t}/api/journal_entries/bulk_update/` | Atualizar em lote |
| `POST` | `/{t}/api/journal_entries/bulk_delete/` | Excluir em lote |
| `POST` | `/{t}/api/journal_entries/suggest-account/` | Sugerir conta via IA |
| `GET` | `/{t}/api/journal_entries/classification-history/` | Histórico de classificação |
| `POST` | `/{t}/api/journal_entries/derive_from/` | Derivar lançamento |
| `GET` | `/{t}/api/journal_entries/unmatched/` | Não conciliados |

**Filtros de Lançamento:** `tag`, `cliente_erp_id`, `transaction_nf_number`, `transaction_due_date_from`, `transaction_due_date_to`

### Centros de Custo

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{t}/api/cost_centers/` | Listar/criar |
| `GET/PUT/PATCH/DELETE` | `/{t}/api/cost_centers/{id}/` | CRUD |
| `POST` | `/{t}/api/cost_centers/bulk_create/` | Criar em lote |

### Bancos e Contas Bancárias

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{t}/api/banks/` | CRUD bancos |
| `GET/POST` | `/{t}/api/bank_accounts/` | CRUD contas bancárias |
| `GET/POST` | `/{t}/api/bank_transactions/` | CRUD transações bancárias |
| `POST` | `/{t}/api/bank_transactions/bulk_create/` | Criar em lote |
| `POST` | `/{t}/api/bank_transactions/{id}/match_boletos/` | Vincular boletos |
| `POST` | `/{t}/api/bank_transactions/suggest_matches/` | Sugerir correspondências |

**Filtros de Transação Bancária:** `tag`, `cliente_erp_id`

### Histórico de Saldos e Comparações

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/{t}/api/balance-history/` | Histórico de saldos |
| `POST` | `/{t}/api/balance-history/recalculate/` | Recalcular histórico |
| `GET` | `/{t}/api/bank-book-daily-balances/` | Comparação banco vs livro |
| `GET` | `/{t}/account_summary/` | Resumo por conta |

### Embeddings

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/{t}/embeddings/health/` | Saúde dos embeddings |
| `GET` | `/{t}/embeddings/missing-counts/` | Contagem sem embedding |
| `POST` | `/{t}/embeddings/backfill/` | Preencher embeddings |
| `POST` | `/{t}/embeddings/search/` | Busca semântica |
| `GET` | `/{t}/embeddings/test/` | Teste rápido |

---

## 15.5 Conciliação Bancária

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{t}/api/reconciliation/` | CRUD conciliações (status: `pending`, `open`, `matched`, `unmatched`, `review`, `approved`) |
| `GET` | `/{t}/api/reconciliation/summaries/` | Sumários por status (inclui contagem de `open`/parciais) |
| `GET` | `/{t}/api/reconciliation/export-unreconciled-report/` | Excel com pendências (inclui ClienteErpId, DueDate, NFNumber) |
| `POST` | `/{t}/api/reconciliation/bulk_create/` | Criar em lote |
| `GET/POST` | `/{t}/api/reconciliation_configs/` | CRUD configurações |
| `GET/POST` | `/{t}/api/reconciliation-pipelines/` | CRUD pipelines |
| `GET/POST` | `/{t}/api/reconciliation-tasks/` | CRUD tarefas |
| `GET/POST` | `/{t}/api/reconciliation-rules/` | CRUD regras |
| `POST` | `/{t}/api/reconciliation-rules/propose/` | Propor regras |
| `POST` | `/{t}/api/reconciliation-rules/validate/` | Validar regra |
| `GET` | `/{t}/reconciliation-dashboard/` | Dashboard |
| `POST` | `/{t}/api/reconciliation-metrics/recalculate/` | Recalcular métricas |
| `POST` | `/{t}/api/reconciliation-record-tags/` | Tags em lote (atribuir/remover tags em JEs e bank transactions) |

**Status de conciliação:** `open` = parcial (vinculação em andamento); `matched` = conciliada; ver [seção 6.4](06-conciliacao-bancaria.md) para detalhes

---

## 15.6 Demonstrações Financeiras

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{t}/api/financial-statement-templates/` | CRUD templates |
| `POST` | `/{t}/api/financial-statement-templates/{id}/set_default/` | Definir padrão |
| `POST` | `/{t}/api/financial-statement-templates/{id}/duplicate/` | Duplicar |
| `GET` | `/{t}/api/financial-statement-templates/suggest_templates/` | Sugerir templates |
| `GET/POST` | `/{t}/api/financial-statements/` | CRUD demonstrativos |
| `POST` | `/{t}/api/financial-statements/generate/` | Gerar demonstrativo |
| `POST` | `/{t}/api/financial-statements/preview/` | Preview |
| `POST` | `/{t}/api/financial-statements/{id}/finalize/` | Finalizar |
| `POST` | `/{t}/api/financial-statements/{id}/archive/` | Arquivar |
| `GET` | `/{t}/api/financial-statements/{id}/export_pdf/` | Exportar PDF |
| `GET` | `/{t}/api/financial-statements/{id}/export_excel/` | Exportar Excel |
| `GET` | `/{t}/api/financial-statements/{id}/export_html/` | Exportar HTML |
| `GET` | `/{t}/api/financial-statements/{id}/export_markdown/` | Exportar Markdown |
| `GET` | `/{t}/api/financial-statements/time_series/` | Série temporal |
| `POST` | `/{t}/api/financial-statements/quick_income_statement/` | DRE rápida |
| `POST` | `/{t}/api/financial-statements/quick_balance_sheet/` | Balanço rápido |
| `POST` | `/{t}/api/financial-statements/detailed_income_statement/` | DRE detalhada |
| `POST` | `/{t}/api/financial-statements/detailed_balance_sheet/` | Balanço detalhado |
| `POST` | `/{t}/api/financial-statements/detailed_cash_flow/` | Fluxo de caixa detalhado |
| `GET/POST` | `/{t}/api/financial-statement-comparisons/` | CRUD comparações |
| `GET` | `/{t}/api/financial-statement-comparisons/{id}/comparison_data/` | Dados da comparação |
| `POST` | `/{t}/financial-statements/template-preview/` | Preview de template |

---

## 15.7 Entidades

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{t}/api/entities/` | CRUD entidades |
| `GET/PUT/PATCH/DELETE` | `/{t}/api/entities/{id}/` | Detalhe/editar/excluir |
| `GET` | `/{t}/api/entities/{id}/context-options/` | Opções de contexto |
| `GET` | `/{t}/api/entities/{id}/effective-context/` | Contexto efetivo |
| `GET` | `/{t}/api/entities-mini/` | Lista compacta |
| `GET` | `/{t}/entity-tree/{company_id}/` | Árvore de entidades |
| `GET` | `/{t}/entities-dynamic-transposed/` | Visão transposta |

---

## 15.8 Faturamento (Billing)

### Parceiros e Produtos

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{t}/api/business_partner_categories/` | CRUD categorias parceiros |
| `GET/POST` | `/{t}/api/business_partners/` | CRUD parceiros |
| `GET/POST` | `/{t}/api/product_service_categories/` | CRUD categorias produtos |
| `GET/POST` | `/{t}/api/product_services/` | CRUD produtos/serviços |
| `GET/POST` | `/{t}/api/contracts/` | CRUD contratos |
| `GET/POST` | `/{t}/api/invoices/` | CRUD faturas |
| `GET/POST` | `/{t}/api/invoice_lines/` | CRUD linhas de fatura |

### Nota Fiscal Eletrônica

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/{t}/api/nfe/import/` | Importar NF-e |
| `POST` | `/{t}/api/nfe/eventos/import/` | Importar eventos |
| `GET` | `/{t}/api/nfe/` | Listar NF-e |
| `GET` | `/{t}/api/nfe/{id}/` | Detalhe |
| `GET` | `/{t}/api/nfe/{id}/resumo/` | Resumo |
| `GET` | `/{t}/api/nfe/{id}/analises/` | Análises |
| `GET` | `/{t}/api/nfe/{id}/timeline/` | Timeline |
| `GET` | `/{t}/api/nfe/{id}/timeline-por-chave/` | Timeline por chave |
| `GET` | `/{t}/api/nfe/canceladas/` | Canceladas |
| `GET` | `/{t}/api/nfe/com-cce/` | Com carta de correção |
| `POST` | `/{t}/api/nfe/{id}/manifestacao/` | Manifestação |
| `GET` | `/{t}/api/nfe-itens/` | Listar itens |
| `GET` | `/{t}/api/nfe-eventos/` | Listar eventos |

---

## 15.9 Recursos Humanos

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{t}/api/positions/` | CRUD cargos |
| `GET/POST` | `/{t}/api/employees/` | CRUD funcionários |
| `GET/POST` | `/{t}/api/timetracking/` | CRUD ponto |
| `GET/POST` | `/{t}/api/kpis/` | CRUD KPIs |
| `GET/POST` | `/{t}/api/bonuses/` | CRUD bônus |
| `GET/POST` | `/{t}/api/recurring-adjustments/` | CRUD ajustes recorrentes |
| `GET/POST` | `/{t}/api/payrolls/` | CRUD folha de pagamento |
| `POST` | `/{t}/api/payrolls/generate-monthly/` | Gerar folha mensal |
| `POST` | `/{t}/api/payrolls/{id}/recalculate/` | Recalcular folha |
| `POST` | `/{t}/api/payrolls/bulk-update-status/` | Atualizar status em lote |

---

## 15.10 Estoque (Inventory)

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{t}/api/inventory/warehouses/` | CRUD almoxarifados |
| `GET/POST` | `/{t}/api/inventory/uom/` | CRUD unidades de medida |
| `GET/POST` | `/{t}/api/inventory/uom-conversions/` | CRUD conversões |
| `GET` | `/{t}/api/inventory/movements/` | Listar movimentações |
| `POST` | `/{t}/api/inventory/movements/manual/` | Movimentação manual |
| `POST` | `/{t}/api/inventory/movements/ingest_nf/` | Ingerir NF-e |
| `POST` | `/{t}/api/inventory/movements/ingest_pending/` | Ingerir pendentes |
| `GET` | `/{t}/api/inventory/balances/` | Saldos de estoque |
| `GET/PATCH` | `/{t}/api/inventory/alerts/` | Alertas |
| `POST` | `/{t}/api/inventory/costing/compute/` | Computar custeio |
| `GET` | `/{t}/api/inventory/comparison/report/` | Relatório comparativo |
| `GET` | `/{t}/api/inventory/comparison/sku/` | Comparação por SKU |
| `GET` | `/{t}/api/inventory/comparison/movement/` | Comparação por movimentação |

---

## 15.11 Integrações ERP

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{t}/api/connections/` | CRUD conexões |
| `GET` | `/{t}/api/api-definitions/` | Listar definições de API |
| `GET/POST` | `/{t}/api/sync-jobs/` | CRUD jobs de sync |
| `POST` | `/{t}/api/sync-jobs/{id}/run/` | Executar sync |
| `POST` | `/{t}/api/sync-jobs/{id}/dry_run/` | Dry run |
| `GET` | `/{t}/api/sync-runs/` | Listar execuções |
| `GET` | `/{t}/api/raw-records/` | Listar registros brutos |
| `GET` | `/{t}/api/raw-records/{id}/data/` | Dados do registro |
| `POST` | `/{t}/api/raw-records/{id}/backfill-external-id/` | Backfill external ID |
| `POST` | `/{t}/api/build-payload/` | Construir payload |
| `POST` | `/{t}/api/etl-import/` | Importar via ETL |

---

## 15.12 ETL e Importação

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/{t}/api/core/etl/analyze/` | Analisar planilha |
| `POST` | `/{t}/api/core/etl/preview/` | Preview da importação |
| `POST` | `/{t}/api/core/etl/execute/` | Executar importação |
| `GET` | `/{t}/api/core/etl/logs/` | Logs de importação |
| `GET` | `/{t}/api/core/etl/logs/{id}/error-report/` | Relatório de erros |
| `GET/POST` | `/api/core/etl/transformation-rules/` | CRUD regras de transformação |
| `GET` | `/api/core/etl/transformation-rules/available_models/` | Modelos disponíveis |
| `GET` | `/{t}/api/core/import/template/` | Baixar template de importação (Excel) |
| `POST` | `/{t}/api/core/import/` | Importar via template (suporta `__erp_id`, `*_erp_id`) |

**Colunas especiais na importação:** `__row_id` (upsert/delete por PK), `__erp_id` (upsert/delete por `cliente_erp_id`), `*_erp_id` (resolve FK por `cliente_erp_id` do modelo relacionado). Ver [seção 11.4b](11-etl-importacao.md) para detalhes e exemplos.

---

## 15.13 Regras

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/api/core/substitution-rules/` | CRUD regras de substituição |
| `GET/POST` | `/api/core/integration-rules/` | CRUD regras de integração |
| `POST` | `/api/core/validate-rule/` | Validar regra |
| `POST` | `/api/core/test-rule/` | Testar regra |
| `POST` | `/api/core/bulk-import/` | Importação em massa |
| `POST` | `/api/core/bulk-import-preview/` | Preview de importação |
| `POST` | `/api/core/merge-records/` | Merge de registros |

---

## 15.14 Tarefas e Celery

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/api/tasks/` | Listar tarefas |
| `GET` | `/api/tasks/{id}/` | Detalhe da tarefa |
| `POST` | `/api/tasks/{id}/stop/` | Parar tarefa |
| `GET` | `/api/tasks/types/` | Tipos de tarefa |
| `GET` | `/api/tasks/statistics/` | Estatísticas |
| `GET` | `/api/celery/queues/` | Status das filas |
| `GET` | `/api/celery/results/` | Resultados |

---

## 15.15 Base de Conhecimento

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{t}/api/knowledge-bases/` | CRUD bases |
| `POST` | `/{t}/api/knowledge-bases/{id}/documents/` | Upload documentos |
| `POST` | `/{t}/api/knowledge-bases/{id}/ask/` | Fazer pergunta |
| `GET` | `/{t}/api/documents/` | Listar documentos |
| `POST` | `/{t}/api/knowledge-bases/answers/{id}/feedback/` | Feedback |

---

## 15.16 Chat e IA

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/api/chat/ask/` | Perguntar com contexto |
| `POST` | `/api/chat/ask_nocontext/` | Perguntar sem contexto |
| `POST` | `/api/chat/flexible/` | Chat flexível |
| `POST` | `/api/chat/diag/` | Diagnóstico do chat |

---

## 15.17 Índices Financeiros

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/api/core/financial_indices/` | CRUD índices |
| `GET` | `/api/core/financial_indices/{id}/quotes/` | Cotações do índice |
| `GET` | `/api/core/financial_indices/{id}/forecast/` | Previsões do índice |
| `GET/POST` | `/api/core/index_quotes/` | CRUD cotações |
| `GET/POST` | `/api/core/index_forecasts/` | CRUD previsões |
| `POST` | `/api/core/rrule_preview/` | Preview de recorrência |

---

## 15.18 Introspecção (Meta API)

| Método | Endpoint | Auth | Descrição |
|--------|----------|------|-----------|
| `GET` | `/api/meta/health/` | Não | Status do sistema |
| `GET` | `/api/meta/endpoints/` | Sim | Todos os endpoints |
| `GET` | `/api/meta/models/` | Sim | Todos os modelos |
| `GET` | `/api/meta/models/{name}/` | Sim | Detalhe do modelo |
| `GET` | `/api/meta/models/{name}/relationships/` | Sim | Relacionamentos |
| `GET` | `/api/meta/enums/` | Sim | Enums/choices |
| `GET` | `/api/meta/filters/` | Sim | Filtros disponíveis |
| `GET` | `/api/meta/capabilities/` | Sim | Capacidades |
| `GET` | `/api/meta/docs/` | Sim | Índice de toda a documentação (árvore + lista de arquivos) |
| `GET` | `/api/meta/docs/{path}` | Sim | Conteúdo de um arquivo de documentação (markdown) |

---

## 15.19 Outros

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/api/activity/` | Feed de atividades |
| `GET` | `/api/tutorial/` | Tutoriais |
| `GET` | `/jobs/` | Listar jobs (legado) |
| `GET` | `/jobs/{id}/` | Detalhe job (legado) |
| `POST` | `/jobs/{id}/cancel/` | Cancelar job (legado) |

---

> **Nota:** `{t}` representa o identificador do tenant (subdomínio da empresa). Substitua pelo subdomínio real (ex: `acme`).

> **Dica:** Para a referência mais atualizada e dinâmica, consulte `/api/meta/endpoints/` que é gerada automaticamente a partir do código.

---

*Anterior: [14 — Recursos Avançados](14-recursos-avancados.md) · [Voltar ao Índice](README.md)*

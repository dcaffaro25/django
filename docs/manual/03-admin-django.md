# 03 — Painel Administrativo (Django Admin)

O Django Admin é a interface de administração da plataforma. Ele permite gerenciar cadastros, realizar operações em lote e acessar dados de forma rápida e eficiente.

---

## 3.1 Acessando o Admin

**URL:** `https://servidor.com/admin/`

**Requisitos:** Usuário com flag `is_staff = True` ou `is_superuser = True`.

Após o login, você verá a lista de módulos organizados por aplicação:

| Aplicação no Admin | Módulos Disponíveis |
|--------------------|---------------------|
| **Multitenancy** | Companies, Entities, Substitution Rules, Users |
| **Accounting** | Accounts, Banks, Bank Accounts, Bank Transactions, Cost Centers, Currencies, Financial Statements, Journal Entries, Reconciliations, Transactions, e mais |
| **Billing** | Business Partners, Contracts, Invoices, NF-e, Products/Services |
| **HR** | Positions, Employees, Time Tracking, KPIs, Bonuses, Payrolls |
| **Inventory** | Warehouses, Stock Movements, Inventory Balances, Costing Config, Alerts |
| **ERP Integrations** | Connections, API Definitions, Sync Jobs, Sync Runs, Raw Records |
| **Knowledge Base** | Knowledge Bases, Documents, Answers, Feedback |
| **Core** | Jobs, Action Events, Financial Indices |

---

## 3.2 Funcionalidades Gerais

### Listagem de Registros

Ao clicar em um modelo, você vê a listagem com:

- **Colunas configuráveis** — cada modelo exibe campos relevantes
- **Filtros laterais** — filtre por empresa, status, data, tipo, etc.
- **Campo de busca** — pesquisa rápida em campos de texto
- **Paginação** — padrão de 100 itens por página (configurável via filtro "Rows per page")

> **Dica:** O filtro **"Rows per page"** permite exibir 25, 50, 100, 250, 500 ou 1000 registros por vez. A preferência é salva na sessão.

### Ações em Lote

A maioria dos modelos suporta **ações em lote**:

1. Selecione os registros usando os checkboxes
2. Escolha a ação no dropdown no topo da listagem
3. Clique em "Go"

**Ações comuns:**

| Ação | Descrição | Disponível em |
|------|-----------|---------------|
| **Delete selected** | Exclusão padrão do Django (com confirmação) | Todos os modelos |
| **Fast delete selected** | Exclusão rápida sem página de confirmação | Transactions, Journal Entries, Bank Transactions, NF-e e mais |
| **Delete bank transactions only** | Remove apenas as transações bancárias | Bank Transactions |
| **Delete bank transactions with reconciliations** | Remove transações bancárias e suas conciliações | Bank Transactions |

> **Atenção:** A ação "Fast delete" não exibe página de confirmação. Use com cuidado!

### Campos de Auditoria

A maioria dos registros possui campos de auditoria exibidos automaticamente:

| Campo | Descrição |
|-------|-----------|
| `created_at` | Data/hora de criação |
| `updated_at` | Data/hora da última modificação |
| `created_by` | Usuário que criou |
| `updated_by` | Usuário que fez a última modificação |
| `is_deleted` | Indicador de exclusão lógica (soft delete) |

---

## 3.3 Módulo Multitenancy (Empresas e Usuários)

### Empresas (Companies)

Cada empresa é um **tenant** — um espaço isolado de dados.

**Campos principais:**
- `name` — Nome da empresa (único)
- `subdomain` — Identificador usado nas URLs (único)

**No Admin:**
- Liste e edite empresas
- Veja o **resumo de conciliação** no endpoint via API

### Entidades (Entities)

Entidades representam a **hierarquia organizacional** dentro de uma empresa.

**Campos principais:**
- `name` — Nome da entidade
- `parent` — Entidade-pai (hierarquia em árvore)
- `erp_id` — ID no ERP externo
- `inherit_accounts` — Herdar contas do pai
- `inherit_cost_centers` — Herdar centros de custo do pai

**No Admin:** Hierarquia visível em árvore (MPTT). Ao adicionar uma entidade, defina o pai para posicioná-la na hierarquia.

### Regras de Substituição (SubstitutionRule)

As regras de substituição fazem o papel de **tabela "de-para"** durante importações.

**Campos principais:**
- `model_name` — Modelo alvo (ex: `Transaction`, `JournalEntry`)
- `field_name` — Campo alvo (ex: `description`, `account`)
- `match_type` — Tipo de correspondência (`exact`, `contains`, `regex`, `startswith`, etc.)
- `match_value` — Valor a ser encontrado
- `substitution_value` — Valor de substituição
- `filter_conditions` — Condições JSON adicionais para aplicação

**No Admin:** Filtro por empresa, visualização prévia das condições em formato compacto.

> **Dica:** Use regras de substituição para normalizar dados durante importações ETL. Veja [13 — Regras de Automação](13-regras-automacao.md).

### Usuários

**Campos além do padrão Django:**
- `must_change_password` — Força troca de senha no próximo login
- `email_last_sent_at` — Último envio de email

**No Admin:** Gerencie permissões, groups, e flags `is_staff` / `is_superuser`.

---

## 3.4 Módulo Contabilidade

### Contas (Accounts)

O plano de contas é uma **árvore hierárquica** (MPTT):

```
1       Ativo
1.1       Ativo Circulante
1.1.1       Caixa e Equivalentes
1.1.1.001     Banco do Brasil C/C
1.1.2       Contas a Receber
1.2       Ativo Não Circulante
2       Passivo
3       Patrimônio Líquido
4       Receitas
5       Despesas
```

**No Admin:**
- **Filtros:** empresa, moeda, conta-pai, direção da conta
- **Busca:** por nome ou código da conta
- **Autocomplete:** para conta-pai, moeda e conta bancária
- **Ação especial:** Edição em lote de contas (selecione múltiplas contas e altere campos como moeda, direção, pai)

> **Avançado:** Cada conta pode ter um **vetor de embedding** para busca semântica (usado pela conciliação e sugestões de classificação).

### Transações (Transactions)

**No Admin:**
- **Colunas:** data, descrição, valor, moeda, entidade, estado, contagem de lançamentos
- **Filtros:** entidade, moeda, estado (rascunho/postado/cancelado), data
- **Inline:** Lançamentos contábeis (Journal Entries) são editados direto na tela da transação
- **Ações:** fast delete, postagem, cancelamento
- **Busca numérica:** buscar por ID da transação ou ID de lançamentos relacionados

### Lançamentos Contábeis (Journal Entries)

**No Admin:**
- **Colunas:** transação (link clicável), conta, centro de custo, débito, crédito, estado, tag
- **Filtros:** conta, centro de custo, estado, tag
- **Autocomplete:** para conta e centro de custo

### Transações Bancárias (Bank Transactions)

**No Admin:**
- **Colunas:** conta bancária, data, valor, descrição, status
- **Filtros:** conta bancária, moeda, status
- **Ações especiais:**
  - `Delete bank transactions only` — remove só as transações
  - `Delete bank transactions with reconciliations` — remove transações e conciliações associadas

### Conciliações (Reconciliations)

**No Admin:**
- Visualização dos vínculos entre lançamentos contábeis e transações bancárias
- Campos M2M (`filter_horizontal`) para Journal Entries e Bank Transactions

---

## 3.5 Módulo Faturamento (Billing)

### Parceiros Comerciais (Business Partners)

**No Admin:**
- Cadastro de clientes e fornecedores
- Hierarquia de categorias (MPTT)
- Vínculo com moeda padrão

### Produtos e Serviços (Product Services)

**No Admin:**
- Cadastro com categorias hierárquicas
- Contas contábeis de estoque vinculadas (para integração com módulo de estoque):
  - Conta de estoque, COGS, receita de venda, ajuste de estoque, etc.

### Notas Fiscais (NF-e)

**No Admin:**
- **Colunas:** chave de acesso, número, série, emitente, destinatário, valor total, status
- **Filtros:** empresa, data de emissão, status
- **Inlines:** Itens da NF-e e Referências são editados dentro da NF-e
- **Ação:** fast delete

> **Avançado:** Eventos de NF-e (cancelamento, carta de correção, manifestação) são gerenciados separadamente no admin.

### Contratos e Faturas

- **Contratos:** Vínculo entre empresa, parceiro comercial e índice financeiro
- **Faturas:** Com linhas de fatura (inline) vinculadas a produtos/serviços

---

## 3.6 Módulo RH

Os seguintes modelos estão registrados com interface básica (sem customizações avançadas):

| Modelo | Descrição |
|--------|-----------|
| **Position** | Cargos com faixa salarial |
| **Employee** | Funcionários vinculados a cargo |
| **TimeTracking** | Registro de horas mensais |
| **KPI** | Indicadores de desempenho |
| **Bonus** | Bonificações |
| **RecurringAdjustment** | Ajustes recorrentes na folha |
| **Payroll** | Folha de pagamento |

> **Dica:** Para operações em lote no RH (geração de folha mensal, recálculo), use a API — o admin oferece apenas CRUD básico.

---

## 3.7 Módulo Estoque (Inventory)

| Modelo no Admin | Descrição |
|----------------|-----------|
| **Warehouse** | Almoxarifados/depósitos |
| **UnitOfMeasure** | Unidades de medida (kg, un, cx...) |
| **UoMConversion** | Conversões entre unidades |
| **StockMovement** | Movimentações de estoque (imutáveis) |
| **InventoryLayer** | Camadas FIFO/custo médio |
| **InventoryBalance** | Saldos atuais por produto/almoxarifado |
| **TenantCostingConfig** | Configuração de custeio por empresa |
| **InventoryValuationSnapshot** | Fotos da valoração do estoque |
| **CogsAllocation** | Alocação de custo dos produtos vendidos |
| **AccountingImpact** | Impactos contábeis gerados pelo estoque |
| **InventoryAlert** | Alertas de estoque (mínimo, divergência, etc.) |

---

## 3.8 Módulo Integrações ERP

### Providers (Provedores)

Cadastro dos ERPs suportados (ex: Omie). Campos: `name`, `slug`, `base_url`.

### Connections (Conexões)

Credenciais da empresa para acessar o ERP externo:
- `company` + `provider` (únicos por par)
- `app_key` / `app_secret` (credenciais Omie)
- `is_active`

> **Dica no Admin:** A `app_key` é exibida de forma **mascarada** na listagem para segurança.

### API Definitions (Definições de API)

Catálogo das chamadas disponíveis no ERP:
- `call` — Nome da chamada (ex: `ListarProdutos`)
- `url` — Endpoint da API
- `method` — Método HTTP
- `param_schema` — Esquema de parâmetros padrão (JSON)
- `transform_config` — Configuração de extração dos registros (JSON)

> **Avançado:** Edite `transform_config` apenas pelo admin ou diretamente no banco. O serializer da API não expõe esse campo.

### Sync Jobs (Jobs de Sincronização)

Vínculos entre conexão + definição de API + parâmetros extras:
- `name` — Nome descritivo do job
- `extra_params` — Override de parâmetros (JSON)
- `schedule_rrule` — Regra de recorrência iCal (ex: `FREQ=HOURLY;INTERVAL=6`)

### Sync Runs e Raw Records

- **Sync Runs:** Histórico de execuções com status, contagens, erros e diagnósticos
- **Raw Records:** Dados brutos extraídos do ERP (JSON) — útil para debugging

---

## 3.9 Base de Conhecimento (Knowledge Base)

| Modelo | Descrição |
|--------|-----------|
| **KnowledgeBase** | Base de conhecimento por empresa (com integração Gemini) |
| **KnowledgeDocument** | Documentos enviados para a base |
| **Answer** | Respostas geradas pela IA |
| **AnswerFeedback** | Feedback dos usuários sobre as respostas |

---

## 3.10 Módulo Core

| Modelo | Descrição |
|--------|-----------|
| **Job** | Tarefas Celery em andamento (UUID, status, progresso) |
| **ActionEvent** | Feed de atividades/auditoria |
| **FinancialIndex** | Índices financeiros (IGPM, IPCA, CDI, etc.) |
| **IndexQuote** | Cotações históricas dos índices |
| **FinancialIndexQuoteForecast** | Previsões de cotações futuras |

---

## 3.11 Dicas Avançadas do Admin

### Filtros por Empresa (Tenant Scoping)

Modelos que herdam de `CompanyScopedAdmin` automaticamente:
- Filtram campos FK/M2M para mostrar apenas opções da mesma empresa
- Suportam o parâmetro `?company=<id>` na URL de adição para pré-selecionar a empresa

**Exemplo:** Ao adicionar uma transação para a empresa 3:
```
/admin/accounting/transaction/add/?company=3
```

### Busca por ID Numérico

Nos modelos de **Transações** e **Lançamentos Contábeis**, a busca aceita números para encontrar pelo ID:

```
Buscar: 12345
→ Encontra a transação #12345 ou transação cujo lançamento tem ID 12345
```

### Exportação de Dados

Para exportar grandes volumes de dados, utilize a API ao invés do admin:

```bash
# Exportar todas as transações como JSON
curl -H "Authorization: Token ..." \
  "https://servidor.com/acme/api/transactions/?page_size=1000" > transacoes.json

# Exportar demonstrativo como PDF
POST /acme/api/financial-statements/{id}/export_pdf/
```

### Inline Editing

Alguns modelos suportam edição inline (registros-filhos dentro do pai):

| Modelo Pai | Inline |
|-----------|--------|
| Transaction | Journal Entries |
| Financial Statement Template | Line Templates |
| Financial Statement | Lines |
| Nota Fiscal | Items, Referências |

---

## 3.12 Operações de Manutenção via Admin

### Recálculo de Saldo de Contas

Disponível via API:
```bash
POST /acme/api/balance-history/recalculate/
```

### Recálculo de Métricas de Conciliação

```bash
POST /acme/api/reconciliation-metrics/recalculate/
```

### Backfill de Embeddings

```bash
POST /acme/embeddings/backfill/
```

> **Avançado:** Essas operações são processadas em background via Celery. Acompanhe o progresso em **Core → Jobs** no admin.

---

*Anterior: [02 — Primeiros Passos](02-primeiros-passos.md) · Próximo: [04 — Multi-Tenancy e Usuários](04-multitenancy-usuarios.md)*

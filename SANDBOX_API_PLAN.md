# Sandbox API Externa — Plano de Evolução

Plano para evoluir `/integrations/sandbox` de uma ferramenta de
preview-de-pipeline para um workbench completo de criação,
documentação-assistida, exploração e operacionalização de
integrações com APIs externas.

---

## 0. O que já existe (linha de base)

Não refazer. Reusar onde possível.

- **Modelos** (`erp_integrations/models.py`):
  - `ERPProvider` (slug + base_url)
  - `ERPConnection` (per-tenant, app_key + app_secret)
  - `ERPAPIDefinition` (call, url, method, `param_schema` JSON,
    `transform_config`, `unique_id_config`)
  - `ERPSyncPipeline` + `ERPSyncPipelineStep` + `ERPSyncPipelineRun`
  - `ErpApiEtlMapping` (mapping `response_list_key` + `field_mappings`
    para um `target_model`)
- **Executor** (`services/pipeline_service.py`): `_run_steps`
  compartilhado, `execute_pipeline` (DB-backed), `execute_pipeline_spec`
  (sandbox in-memory com caps).
- **Bindings** entre passos: `static`, `jmespath`, `fanout` — validados
  via `_validate_binding`.
- **Endpoints**:
  - `GET/POST /{tenant}/api/sync-pipelines/` (CRUD + `run` / `dry_run`)
  - `GET /{tenant}/api/pipeline-runs/` (histórico)
  - `POST /{tenant}/api/pipeline-sandbox/` (executor preview-only)
- **UI**: `frontend/src/pages/integrations/ApiSandboxPage.tsx` (~745
  linhas). Layout dois painéis (esquerda: passos; direita: diagnóstico
  + preview tabbed table/JSON/projected).
- **Testes**: 13 cobrindo binding validation, fanout, dry_run, caps,
  failure handling, backward-compat com `execute_sync`.

A partir daqui, todo trabalho é **aditivo**.

---

## 1. Definição estruturada de APIs pela tela

> "Permitir definição fácil das APIs pela tela. Criação de campos de
> forma estruturada para depois ser jogado no JSON."

Hoje, o operador edita `ERPAPIDefinition` diretamente no admin Django.
`param_schema` é um JSONField cru. Precisamos de uma tela dedicada que
constroi o JSON a partir de campos validados.

### 1.1 Modelo (`ERPAPIDefinition`)

Manter shape; adicionar metadados:
- `version` (int, default 1) — incrementa a cada salvar; permite
  rollback simples.
- `source` (`enum`: `manual` / `imported` / `discovered` — o último
  vem da Fase 2).
- `documentation_url` (URLField, opcional) — usado pela Fase 2.
- `last_tested_at`, `last_test_outcome` (`success`/`error`/`auth_fail`)
  — alimenta a "saúde da definição" no listing.
- `auth_strategy` (`enum`: `provider_default` / `query_params` /
  `bearer_header` / `basic` / `custom_template`) — hoje o auth tá
  hard-coded no fetch; precisa ser parametrizado para suportar APIs
  fora do Omie.

### 1.2 Form builder (frontend)

Nova página: `/integrations/api-definitions` (lista) e
`/integrations/api-definitions/:id` (editor).

Campos estruturados:
- **Identificação**: `provider`, `call` (slug), `description`.
- **HTTP**: `method`, `url` (com placeholders `{base_url}`,
  `{tenant_id}`, etc.), headers extras.
- **Auth**: estratégia + payload de credenciais (referência simbólica
  a `ERPConnection.app_key` / `app_secret` — nunca digitada na
  definição).
- **Param schema** (lista editável):
  - row = `{ name, type, required, default, description, location }`
  - `type` ∈ `string|int|number|boolean|date|enum|object|array`
  - `location` ∈ `body|query|path|header` (hoje só body funciona;
    expandir o request builder em paralelo).
  - validação ao salvar: tipos consistentes, defaults convertíveis.
- **Pagination spec**:
  - `mode` ∈ `none|page_number|cursor|offset`
  - campos correspondentes (page_param, page_size_param, cursor_path,
    `next_cursor_param`).
- **Response shape**:
  - `records_path` (JMESPath) — onde fica o array de itens.
  - `total_path` (opcional) — para barra de progresso real.
  - exemplo redacted (1 item, capturado durante a Fase 3 e armazenado
    para referência na lista).

### 1.3 Backend

- Serializer estruturado (`APIDefinitionWriteSerializer`) com
  validators por campo. Ele **monta** o JSON `payload` template e o
  `param_schema` final.
- Endpoints: `GET/POST/PATCH /{tenant}/api/api-definitions/`,
  `POST .../validate/` (compila e devolve erros sem salvar),
  `POST .../test-call/` (faz uma chamada real com 1 página + redact —
  reusa `fetch_and_parse_page` da Fase 3).

### 1.4 Entregável

- Operador cria uma `ERPAPIDefinition` válida sem tocar JSON.
- A definição já carrega `pagination` e `records_path` que o executor
  passa a usar (substituir o atual unwrap hard-coded em
  `omie_sync_service`).

---

## 2. Auto-descoberta a partir de URL de documentação

> "Função de jogar link da página de documentação da API e o sistema
> já tentar identificar sozinho as APIs."

Boa-fé: cobrir os formatos mais comuns; quando não der, deixa claro o
que foi entendido e o operador conclui na Fase 1.

### 2.1 Estratégias de detecção (em ordem)

1. **OpenAPI / Swagger**: tenta `<url>`, `<url>/swagger.json`,
   `<url>/openapi.json`, `<url>/v3/api-docs`. Parse `paths` →
   gera 1 `ERPAPIDefinition` candidata por endpoint, com
   `param_schema` derivado de `parameters` + `requestBody`.
2. **Postman Collection** (se `Content-Type: application/json` +
   `info.schema` apontando pra postman.com): parse `item[]` →
   mesma transformação.
3. **HTML scraping com heurística** (fallback): puxa a página, busca
   blocos `<code>`/`<pre>` com URL + JSON exemplo. Tenta inferir
   `method`, `url`, `payload`. Confidence baixa por construção.
4. **LLM-assisted parse** (opcional, com flag): se o tenant habilitar
   `BillingTenantConfig.allow_llm_doc_parse`, manda a página para um
   modelo com prompt estruturado pedindo lista de
   `{call, method, url, params}`. Output JSON-only, validado contra
   um schema antes de criar candidatas.

### 2.2 Fluxo

- Tela: `/integrations/api-definitions/discover`
- Inputs: URL + provider (opcional).
- Output: lista de candidatas com checkbox + diff lado-a-lado
  contra `ERPAPIDefinition`s já existentes pra mesmo provider/call.
- Botão **"Importar selecionadas"** cria as definições com
  `source='discovered'` e `version=1`. O operador ainda passa por
  Fase 1 pra validar antes de marcar `is_active=True`.

### 2.3 Backend

- `services/api_discovery_service.py` (novo):
  - `discover_from_url(url, provider_id) -> List[CandidateAPIDef]`
  - cada candidata carrega `confidence` (0..1) e `source_strategy`
    (openapi/postman/html/llm).
- Endpoint: `POST /{tenant}/api/api-definitions/discover/`.
- Cache leve no resultado bruto (memória, 10min) — operador costuma
  iterar várias vezes refinando filtros.

### 2.4 Entregável

- Cole URL → sistema lista 5–80 endpoints candidatos com schema
  pré-preenchido. Operador edita 2–3 campos por candidata em vez
  de criar do zero.

---

## 3. Sandbox com joins entre APIs

> "Tela de teste de API deve permitir que façamos joins, a tela de
> join deve apresentar as colunas de um lado e de outro e o usuário
> escolher como deve ser usado. Após selecionar a primeira API o
> sistema deve rodar uma consulta pequena para apresentar um exemplo
> da estrutura do output. O mesmo vale para as consultas subsequentes
> que serão usadas para montar o join. O resultado dessas seleções
> após join deve ser apresentado na direita."

Esta é a evolução do sandbox atual. O modelo de `param_bindings` já
faz o equivalente a um join "lookup-em-cadeia". Falta:

1. **Auto-probe**: rodar 1 página assim que o operador escolhe a API
   pra mostrar a estrutura do output (sem ele clicar Run ainda).
2. **Visual join builder**: lado-a-lado das colunas das duas APIs,
   click pra mapear.
3. **Resultado join consolidado** no painel direito (não só por-step).

### 3.1 Auto-probe

- No `ApiSandboxPage`, ao trocar `api_definition` num passo, chamar
  automaticamente `POST /api/pipeline-sandbox/` com **só esse passo**,
  `max_pages=1`, `max_fanout=1`. Resultado vai para um cache local
  React.
- Estrutura derivada:
  - `columns` = chaves do primeiro item (recursivo até nível 2 →
    `endereco.cidade` aparece como coluna selecionável).
  - `sample_values` = primeiros 3 valores não-null de cada coluna.
- Painel "Estrutura" abaixo do passo mostra a tabela
  `coluna · tipo inferido · 3 valores exemplo`. Botão "Re-amostrar"
  re-executa.

### 3.2 Join builder

Novo widget entre passos quando o passo N tem ≥ 1 binding `jmespath`
ou `fanout`:

```
┌───────────────────────┐    ┌───────────────────────┐
│ Passo 1: ListarPedidos│    │ Passo 2: ListarCliente│
│  • id                 │───▶│  • cliente_id         │
│  • cliente_id    ━━━━━┼━━━▶│  • razao_social       │
│  • valor_total        │    │  • cnpj               │
│  • data_criacao       │    │                       │
└───────────────────────┘    └───────────────────────┘
                Mode: fanout
                Into: cliente_codigo
```

Operador clica numa coluna do passo 1 (lado esquerdo) e arrasta /
clica numa coluna do passo 2 (param do request, lado direito). O
sistema:
- Infere `mode='fanout'` se a coluna do lado 1 é array, senão
  `jmespath` (lookup 1:1).
- Gera o `expression` JMESPath a partir do path da coluna
  selecionada.
- Mostra preview da expressão em texto ("Para cada pedido, vai
  buscar o cliente correspondente").

Reusa **toda** a infra de `param_bindings` que já existe — só dá uma
camada visual.

### 3.3 Resultado consolidado

Painel direito hoje mostra `preview_by_step`. Adicionar uma aba
**"Resultado"** que junta os passos via os bindings:
- linhas = output do último passo
- colunas extras = valores que vieram dos passos anteriores via
  binding (lookup reverso através do `_invocation` log que o executor
  já produz).

Implementação no backend: novo helper `_build_joined_preview` em
`pipeline_service.py` que pós-processa `preview_by_step` +
`step_diagnostics.invocations` → array de linhas achatadas. Sem
storage extra.

### 3.4 Entregável

- Operador monta um pipeline ListarPedidos → ListarClientes
  visualmente (sem digitar JMESPath).
- Vê o resultado-com-join na direita: 1 linha por pedido com
  `pedido.id`, `pedido.valor`, `cliente.razao_social`, `cliente.cnpj`.
- Pipeline sai do sandbox pronto pra ser salvo (Fase 4).

---

## 4. Rotinas de importação — periodicidade, incremental, gerenciamento

> "Tela de criação de rotina de importação e gerenciamento de
> importações. Definir periodicidade, quais campos avançam etc.
> trigar uma nova consulta etc."

Hoje `ERPSyncPipeline` tem campo `schedule_rrule` mas sem UI/scheduler
ativo. Duas peças: scheduler (Celery beat) e UI de rotinas.

### 4.1 Modelo

Adicionar a `ERPSyncPipeline`:
- `schedule_rrule` (já existe — wire up Celery beat).
- `is_paused` (BooleanField) — pausar sem deletar.
- `incremental_config` (JSONField):
  ```json
  {
    "field": "data_ultima_alteracao",
    "operator": ">=",
    "param_name": "filtrar_apartir_de",
    "format": "iso8601",
    "lookback_seconds": 300
  }
  ```
- `last_high_watermark` (DateTimeField, null) — o "até onde já
  trouxemos" entre runs.

`ERPSyncPipelineRun` ganha:
- `started_at`, `finished_at` (já tem),
- `triggered_by` (`schedule` / `manual` / `api`),
- `incremental_window_start`, `incremental_window_end`.

### 4.2 Scheduler

- **Celery beat dinâmico**: tabela `django-celery-beat` com
  `PeriodicTask`s gerados a partir de `ERPSyncPipeline.schedule_rrule`.
- Tarefa: `erp_integrations.tasks.run_pipeline_scheduled(pipeline_id)`
  - calcula `incremental_window` a partir de
    `last_high_watermark - lookback_seconds` até `now()`.
  - injeta o param de filtro no primeiro passo via `extra_params`
    sem persistir na definição.
  - se sucesso, atualiza `last_high_watermark` no fim do run.
  - se erro, mantém HW velho (próximo run repete a janela).

### 4.3 UI de rotinas

Nova página `/integrations/rotinas` (lista) +
`/integrations/rotinas/:id` (detalhe).

Lista:
- Pipeline · provider · agendamento · last_run · status · próxima
  execução · botões `Pausar/Retomar` `Rodar agora`.

Detalhe:
- **Aba "Agendamento"**:
  - selector de cron (`every X minutes` / `daily at HH:MM` / `cron
    expression`) → gera `schedule_rrule`.
  - toggle de pausa.
- **Aba "Incremental"**:
  - dropdown do campo do **primeiro passo** que avança (lê do
    `param_schema` da `ERPAPIDefinition`).
  - dropdown do operador (`>=`, `>`).
  - input de `lookback_seconds` (default 300).
  - preview: "Próximo run vai buscar registros com
    `data_alteracao >= 2026-05-04T13:55:00`."
- **Aba "Histórico"**:
  - últimos 50 `ERPSyncPipelineRun` com duração, registros, erros.
  - replay: "Rodar de novo a janela X..Y" (cria um run manual com
    janela explícita, sem mexer no high-watermark).
- **Aba "Saída"**:
  - vincula o pipeline a um `ErpApiEtlMapping` → onde os registros
    importados aterrissam (model alvo + field_mappings).

### 4.4 Entregável

- Operador cria pipeline no sandbox, salva, vai em "Rotinas",
  define "rodar a cada hora trazendo registros novos a partir do
  campo `data_alteracao`" e vê o pipeline rodando sozinho daí em
  diante.
- Histórico mostra cada run, sucesso/falha, janela e contagem.

---

## 5. Conexões com o resto do sistema

Pontos onde a Sandbox-evoluída se ancora no que já existe:

- **`ErpApiEtlMapping`** (já existe) — é o "para onde os registros
  vão" depois do pipeline rodar. Hoje tá desconectado da UI; a Fase
  4 plugga ele explicitamente.
- **`ERPRawRecord`** (já existe) — ainda é o storage intermediário.
  Pipeline persiste com `pipeline_run` FK.
- **Saúde dos Dados** (`/operacao/saude`) — adicionar checks:
  - `check_stale_pipeline_runs` (último run > X horas atrás)
  - `check_pipeline_recent_failures` (taxa de erro nos últimos 7d)
  - CTAs deep-linkam pra `/integrations/rotinas/:id`.
- **Importações** (`/imports`) — UI de upload manual permanece;
  rotinas APIs aparecem como uma fonte adicional no mesmo dashboard
  de "Importações" (gera um job ID equivalente).

---

## 6. Sequência sugerida

Cada fase entrega valor isolado; pular pra qualquer ponto é
viável depois da Fase 1.

| # | Fase | Por quê primeiro |
|---|------|------------------|
| 1 | Definição estruturada (Seção 1) | Destrava todo o resto: discovery (2) gera essas definições, sandbox (3) consome, rotinas (4) executam pipelines feitos delas. Também é a maior dor atual (admin Django). |
| 2 | Auto-descoberta (Seção 2) | Multiplicador da Fase 1 — operador cria 50 APIs em vez de 5. Estratégia OpenAPI/Postman primeiro; HTML/LLM ficam pra depois. |
| 3 | Joins visuais (Seção 3) | Aproveita o sandbox que já existe. Só auto-probe + camada visual + resultado consolidado. Sem mudança de modelo. |
| 4 | Rotinas (Seção 4) | Operacionaliza. Depende de pipelines salvos (já existe) + scheduler (novo) + incremental (novo). Maior peça nova de backend (Celery beat dinâmico, watermarking). |

---

## 7. Riscos / pontos de atenção

- **Auth genérico**: hoje o fetch tá amarrado ao Omie. Generalizar
  `auth_strategy` em `ERPAPIDefinition` toca todo o
  `omie_sync_service`. Faz junto com Fase 1; sem isso, Fase 2 traz
  definições que não rodam.
- **Pagination genérica**: mesma observação. Hoje `MAX_PAGES` +
  unwrap são hard-coded. A `pagination_spec` da Fase 1 substitui.
- **Discovery via LLM**: opt-in por tenant (
  `BillingTenantConfig.allow_llm_doc_parse`), nunca passar credenciais
  no prompt, redact obrigatório, output validado contra JSON schema.
- **High-watermark race**: dois runs simultâneos do mesmo pipeline
  sobreescrevem o HW. Adicionar `select_for_update` + lock no
  `ERPSyncPipeline` durante o run, ou usar `concurrency=1` no Celery.
- **Tamanho do JSON salvo**: o `first_payload_redacted` que a Fase 3
  guarda como exemplo precisa ter cap de tamanho (~200KB) ou some
  da UI rapidinho.

---

## 8. Tracking

Cada fase vira uma série de PRs/commits seguindo o padrão
`feat(integrations): ...`. Status atualizado neste arquivo.

- [ ] **Fase 1** — Definição estruturada + auth/pagination genéricos
- [ ] **Fase 2** — Discovery (OpenAPI + Postman; HTML/LLM opcional)
- [ ] **Fase 3** — Auto-probe + join builder visual + resultado
      consolidado
- [ ] **Fase 4** — Rotinas: scheduler + incremental + UI de
      gerenciamento + histórico + replay

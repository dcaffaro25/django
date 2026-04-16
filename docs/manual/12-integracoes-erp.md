# 12 — Integrações ERP

O módulo de integrações ERP permite conectar a plataforma Nord a sistemas externos como **Omie** e outros ERPs, sincronizar dados automaticamente e importar registros para o sistema.

---

## 12.1 Arquitetura da Integração

```
┌────────────────┐     ┌──────────────────┐     ┌────────────────┐
│  ERP Externo   │     │  Nord Backend    │     │  Dados de      │
│  (ex: Omie)    │────►│  Sync Service    │────►│  Negócio       │
│                │     │                  │     │                │
│  API REST      │     │  ERPSyncJob      │     │  Transactions  │
│                │     │  ERPSyncRun      │     │  Products      │
│                │     │  ERPRawRecord    │     │  Partners      │
└────────────────┘     └──────────────────┘     └────────────────┘
```

O fluxo completo tem **duas etapas distintas**:

1. **Sincronização** — Chama a API do ERP e salva os dados brutos (`ERPRawRecord`)
2. **ETL** — Transforma os dados brutos em registros de negócio (Products, Transactions, etc.)

> **Importante:** A sincronização e o ETL são etapas separadas. A sincronização apenas armazena dados brutos; o ETL é executado separadamente.

---

## 12.2 Configuração Inicial

### Passo 1: Verificar o Provider

O provider (ex: Omie) deve estar cadastrado no sistema:

```bash
GET /acme/api/api-definitions/?provider__slug=omie
```

### Passo 2: Criar a Conexão (ERPConnection)

Cadastre as credenciais da sua empresa no ERP:

```bash
POST /acme/api/connections/
{
  "provider": 1,
  "app_key": "sua_app_key_aqui",
  "app_secret": "seu_app_secret_aqui",
  "is_active": true
}
```

> **Atenção:** As credenciais são armazenadas de forma segura. No admin, a `app_key` é exibida mascarada.

### Passo 3: Verificar Definições de API

As definições de API descrevem quais chamadas podem ser feitas ao ERP:

```bash
GET /acme/api/api-definitions/
```

**Exemplo de definição (Omie):**

```json
{
  "id": 1,
  "provider": 1,
  "call": "ListarClientes",
  "url": "https://app.omie.com.br/api/v1/geral/clientes/",
  "method": "POST",
  "param_schema": {
    "pagina": {"type": "integer", "default": 1},
    "registros_por_pagina": {"type": "integer", "default": 50},
    "clientesFiltro": {"type": "object"}
  }
}
```

### Passo 4: Criar Job de Sincronização

```bash
POST /acme/api/sync-jobs/
{
  "connection": 1,
  "api_definition": 1,
  "name": "Sync Clientes Omie",
  "is_active": true,
  "extra_params": {
    "registros_por_pagina": 100
  }
}
```

**Campos do Job:**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `connection` | FK | Conexão ERP |
| `api_definition` | FK | Definição de API |
| `name` | string | Nome descritivo |
| `is_active` | boolean | Job ativo |
| `extra_params` | JSON | Parâmetros adicionais para a chamada |
| `schedule_rrule` | string | Regra de recorrência iCal (opcional) |

---

## 12.3 Executando Sincronizações

### Dry Run (Teste sem Salvar)

Antes de executar uma sincronização completa, faça um teste:

```bash
POST /acme/api/sync-jobs/{id}/dry_run/
```

O dry run:
- Executa **apenas a primeira página** da API
- **Não salva** raw records no banco
- Cria um `ERPSyncRun` com diagnósticos
- Roda de forma **síncrona** (resposta imediata)

Use para verificar:
- Credenciais estão funcionando
- URL e chamada estão corretas
- Extração de registros funciona

### Sincronização Completa

```bash
POST /acme/api/sync-jobs/{id}/run/
```

**Resposta:**
```json
{
  "task_id": "abc123-def456-ghi789"
}
```

A sincronização completa:
- Percorre **todas as páginas** da API
- Salva cada registro em `ERPRawRecord`
- Roda em **background via Celery**
- Pode levar vários minutos dependendo do volume

### Acompanhar Execução

```bash
# Via tarefas
GET /api/tasks/{task_id}/

# Via sync runs
GET /acme/api/sync-runs/?job={job_id}
```

---

## 12.4 Configuração de Extração (transform_config)

A `transform_config` na definição de API controla como os registros são extraídos da resposta do ERP.

### Estrutura

```json
{
  "records": {
    "path": "produto_servico_cadastro",
    "fallbackPaths": ["data.items"],
    "autoDiscover": true,
    "rootAsOneRow": false
  }
}
```

| Campo | Descrição |
|-------|-----------|
| `records.path` | Caminho no JSON até o array de registros (ex: `cadastro` ou `data.items`) |
| `records.fallbackPaths` | Caminhos alternativos se o principal falhar |
| `records.autoDiscover` | Se `true`, busca automaticamente o primeiro array de objetos no JSON |
| `records.rootAsOneRow` | Se `true`, trata o JSON inteiro como um único registro |

### Quando Configurar

- Se o `autoDiscover` encontra o array correto → não precisa configurar
- Se falhar (`RecordExtractionError`) → defina `records.path` manualmente

> **Dica:** Use o dry run para verificar se a extração funciona corretamente. Os diagnósticos do `ERPSyncRun` mostram o que foi encontrado.

> **Avançado:** A `transform_config` só pode ser editada pelo **Django Admin** ou diretamente no banco. A API de definições é read-only.

---

## 12.5 Visualizando Resultados

### Listar Execuções (Sync Runs)

```bash
GET /acme/api/sync-runs/?job=1
```

**Campos do Sync Run:**

| Campo | Descrição |
|-------|-----------|
| `status` | `completed`, `failed`, `partial`, `running` |
| `pages_fetched` | Número de páginas processadas |
| `total_records` | Total de registros extraídos |
| `segments_total` | Segmentos planejados (incremental/date_windows) |
| `segments_completed` | Segmentos concluídos com sucesso |
| `failed_segment_label` | Label do segmento que falhou (se aplicável) |
| `errors` | Erros encontrados (JSON) |
| `diagnostics` | Informações de diagnóstico |
| `started_at` / `completed_at` | Timestamps |

### Consultar Registros Brutos (Raw Records)

```bash
# Por sync run
GET /acme/api/raw-records/?sync_run=5

# Por chamada de API
GET /acme/api/raw-records/?api_call=ListarClientes

# Dados de um registro específico
GET /acme/api/raw-records/{id}/data/
```

### Status do Job

O próprio job mantém campos de status:

| Campo | Descrição |
|-------|-----------|
| `last_synced_at` | Última sincronização |
| `last_sync_status` | `never`, `completed`, `failed`, `partial`, `running` |
| `last_sync_record_count` | Registros na última execução |

---

## 12.6 Do Registro Bruto ao Dado de Negócio (ETL)

Após a sincronização, os dados brutos precisam ser transformados em registros de negócio.

### Criando um Mapeamento ETL

```bash
POST /acme/api/etl-mappings/
{
  "company": 1,
  "api_definition": 1,
  "target_model": "BusinessPartner",
  "response_list_key": "clientes_cadastro",
  "field_mappings": {
    "razao_social": "name",
    "cnpj_cpf": "document",
    "email": "email",
    "codigo_cliente_omie": "cliente_erp_id"
  }
}
```

### Executando a Importação ETL

```bash
POST /acme/api/etl-import/
{
  "mapping_id": 1,
  "data": [...],
  "commit": false
}
```

- `commit: false` → Preview (mostra o que seria importado)
- `commit: true` → Executa a importação

### Upsert e Delete via `cliente_erp_id`

O ETL de integrações ERP suporta as mesmas convenções de add/edit/delete do import por template:

- **Upsert automático:** Quando o mapeamento inclui `cliente_erp_id`, o sistema verifica se já existe um registro com esse ID ERP. Se existir, **atualiza**; caso contrário, **cria**.
- **Delete:** Se o `__erp_id` na linha começa com `-`, o registro é **excluído**.
- **FK por ID ERP:** Colunas como `account_erp_id`, `entity_erp_id`, `currency_erp_id` resolvem a FK buscando o registro relacionado pelo `cliente_erp_id`.

**Exemplo: Mapeamento ETL para Transações (Omie Contas a Pagar):**

```bash
POST /acme/api/etl-mappings/
{
  "company": 1,
  "api_definition": 5,
  "target_model": "Transaction",
  "response_list_key": "conta_pagar_cadastro",
  "field_mappings": {
    "codigo_lancamento_omie": "cliente_erp_id",
    "data_vencimento": "due_date",
    "numero_documento_fiscal": "nf_number",
    "valor_documento": "amount",
    "observacao": "description",
    "data_previsao": "date",
    "codigo_cliente_fornecedor_integracao": "entity_erp_id"
  }
}
```

Neste exemplo:
- `codigo_lancamento_omie` → `cliente_erp_id` da transação (permite upsert em re-execuções)
- `data_vencimento` → `due_date` (campo de vencimento na transação)
- `numero_documento_fiscal` → `nf_number` (número da NF na transação)
- `codigo_cliente_fornecedor_integracao` → `entity_erp_id` (resolve Entity via `cliente_erp_id`)

---

## 12.7 Agendamento Automático (schedule_rrule)

Jobs podem ser agendados para execução periódica usando regras iCal RRULE:

```bash
PATCH /acme/api/sync-jobs/{id}/
{
  "schedule_rrule": "FREQ=DAILY;BYHOUR=6;BYMINUTE=0"
}
```

**Exemplos de RRULE:**

| RRULE | Frequência |
|-------|------------|
| `FREQ=HOURLY;INTERVAL=6` | A cada 6 horas |
| `FREQ=DAILY;BYHOUR=6;BYMINUTE=0` | Diariamente às 6h |
| `FREQ=WEEKLY;BYDAY=MO,WE,FR` | Seg, Qua, Sex |
| `FREQ=MONTHLY;BYMONTHDAY=1` | Primeiro dia de cada mês |

### Como Funciona o Scheduler

O **Celery Beat** verifica a cada **15 minutos** (`erp-sync-scheduled-jobs`) se há jobs de sincronização pendentes. A task `run_all_due_syncs`:

1. Busca todos os `ERPSyncJob` ativos com `schedule_rrule` preenchido
2. Exclui jobs que já estão com status `running` (evita execuções duplicadas)
3. Para cada candidato, calcula a **próxima ocorrência** do RRULE a partir do `last_synced_at`
4. Se essa ocorrência é anterior ao momento atual → o job é "due" e é disparado
5. Se o job nunca executou (`last_synced_at` é nulo), ele é considerado due imediatamente

> **Requisito:** O **Celery Beat** e ao menos um **worker** devem estar rodando no servidor para que os agendamentos funcionem.

---

## 12.8 Sincronização Incremental (fetch_config)

Por padrão, um sync job busca **todos os registros** da API a cada execução (`mode: pagination_only`). Para APIs com muitos dados, isso é ineficiente. O campo `fetch_config` permite configurar **busca incremental por data**, garantindo que cada execução traz apenas os dados novos.

### Modos de Fetch

| Modo | Descrição |
|------|-----------|
| `pagination_only` | **(Padrão)** Busca tudo, sem filtro de data |
| `date_windows` | Backfill: divide o período em janelas de N dias e busca todas |
| `incremental_dates` | **Incremental:** busca uma janela de datas por vez, avançando automaticamente |

### Configurando Sincronização Incremental

Para que o job busque apenas dados novos a cada execução:

```bash
PATCH /acme/api/sync-jobs/{id}/
{
  "fetch_config": {
    "mode": "incremental_dates",
    "date_dimension": {
      "from_key": "dDtIncDe",
      "to_key": "dDtIncAte",
      "format": "dd/MM/yyyy",
      "window_days": 7
    },
    "bounds": {
      "start": "2026-01-01"
    }
  }
}
```

**Campos da `fetch_config`:**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `mode` | string | `pagination_only`, `date_windows` ou `incremental_dates` |
| `date_dimension.from_key` | string | Nome do parâmetro de data inicial na API (ex: `dDtIncDe` no Omie) |
| `date_dimension.to_key` | string | Nome do parâmetro de data final na API (ex: `dDtIncAte`) |
| `date_dimension.format` | string | Formato da data (`dd/MM/yyyy` para Omie, ou `YYYY-MM-DD`) |
| `date_dimension.window_days` | int | Tamanho da janela em dias (ex: 7 = uma semana por execução) |
| `bounds.start` | string | Data de início (ISO: `YYYY-MM-DD`) |
| `bounds.end` | string | Data fim fixa (opcional — hard cap) |
| `bounds.end_offset_days` | int | Offset dinâmico para data fim: `0` = hoje, `-1` = ontem (padrão: `-1`) |
| `static_params` | object | Parâmetros fixos adicionais (sobrescreve `extra_params`) |
| `timezone` | string | Timezone para cálculo de "hoje" (padrão: `America/Sao_Paulo`) |

### Como o Cursor Funciona

O modo `incremental_dates` gera **todos os segmentos** entre o cursor (ou `bounds.start`) e a data fim dinâmica (ontem, por padrão) **em uma única execução**. O cursor avança segmento a segmento: após cada segmento bem-sucedido, o cursor é salvo imediatamente. Isso permite **catch-up automático** quando o job está atrasado.

```
Exemplo com window_days: 1, bounds.start: 2026-01-01, hoje: 2026-04-15

Primeira execução (cursor = null):
  → Gera 104 segmentos: Jan 1, Jan 2, ..., Apr 14 (end_offset_days: -1 → ontem)
  → Segmento Jan 1: OK → cursor avança para 2026-01-02
  → Segmento Jan 2: OK → cursor avança para 2026-01-03
  → ...
  → Segmento Apr 14: OK → cursor avança para 2026-04-15
  → Status: completed, segments_total=104, segments_completed=104

Próxima execução (cursor.next_start = "2026-04-15", hoje: 2026-04-16):
  → Gera 1 segmento: Apr 15
  → OK → cursor avança para 2026-04-16
  → Normal daily sync

Se cursor.next_start > bound_end:
  → Nenhum segmento gerado, job encerra com 0 registros
```

O número máximo de segmentos por execução é controlado por `max_segments_per_run` (padrão: 200).

### Comportamento em Caso de Erro

Se um segmento falhar durante o catch-up, o sistema **para imediatamente** no segmento com erro:

```
Execução com cursor.next_start = 2026-01-01, hoje: 2026-04-15

  → Segmento Jan 1: OK → cursor = 2026-01-02
  → Segmento Jan 2: OK → cursor = 2026-01-03
  → ...
  → Segmento Mar 16: ERRO (ex: API retornou 500)
  → Cursor NÃO avança (permanece em 2026-03-16)
  → Status: partial (75 segmentos completos de 104)
  → failed_segment_label: "2026-03-16..2026-03-16"
```

O `ERPSyncRun` registra:

| Campo | Descrição |
|-------|-----------|
| `segments_total` | Segmentos planejados para a execução |
| `segments_completed` | Segmentos concluídos com sucesso |
| `failed_segment_label` | Label do segmento que falhou (ex: `2026-03-16..2026-03-16`) |

Na próxima execução (manual ou via Beat), o sync retoma automaticamente do cursor — ou seja, do segmento que falhou.

### Exemplo Completo: Sync Incremental de Contas a Pagar (Omie)

```bash
POST /acme/api/sync-jobs/
{
  "connection": 1,
  "api_definition": 5,
  "name": "Contas a Pagar — Incremental",
  "is_active": true,
  "schedule_rrule": "FREQ=DAILY;BYHOUR=7;BYMINUTE=0",
  "fetch_config": {
    "mode": "incremental_dates",
    "date_dimension": {
      "from_key": "dDtIncDe",
      "to_key": "dDtIncAte",
      "format": "dd/MM/yyyy",
      "window_days": 1
    },
    "bounds": {
      "start": "2026-04-01"
    }
  }
}
```

Este job:
- Executa **diariamente às 7h** (via RRULE + Celery Beat)
- Busca **1 dia por vez** (window_days: 1)
- Na primeira execução, busca **todos os dias** de 01/04 até ontem (catch-up automático)
- Após alcançar o dia atual, cada execução traz apenas 1 dia novo
- Nunca re-busca dados já trazidos (cursor avança somente após sucesso)

### Retry Manual de Sincronizações com Erro

Quando uma execução falha em um segmento específico, use o endpoint de retry:

```bash
POST /acme/api/sync-jobs/{id}/retry/
```

O retry simplesmente dispara uma nova execução que **retoma do cursor atual** — ou seja, do segmento que falhou.

**Opção avançada — Reposicionar o cursor:**

Se você precisa re-buscar dados de um período anterior (ex: corrigiu a definição de API e quer re-executar desde uma data específica):

```bash
POST /acme/api/sync-jobs/{id}/retry/
{
  "reset_cursor_to": "2026-03-10"
}
```

Isso move o cursor para `2026-03-10` e dispara a execução. Todos os segmentos de `2026-03-10` em diante serão re-processados.

> **Atenção:** `reset_cursor_to` pode causar duplicação de dados em APIs sem `unique_id_config` (dedup). Para APIs com dedup (`on_duplicate: update`), registros idênticos são ignorados e registros alterados são atualizados.

### Backfill com Date Windows

Se você precisa fazer um backfill histórico (buscar todos os dados de um período), use `date_windows`:

```bash
{
  "fetch_config": {
    "mode": "date_windows",
    "date_dimension": {
      "from_key": "dDtIncDe",
      "to_key": "dDtIncAte",
      "format": "dd/MM/yyyy",
      "window_days": 30
    },
    "bounds": {
      "start": "2025-01-01",
      "end": "2025-12-31"
    },
    "max_segments_per_run": 12
  }
}
```

Isso divide o ano em janelas de 30 dias e busca todas em uma execução (máximo 12 segmentos).

### Parâmetros Estáticos (static_params)

Parâmetros que devem ser enviados em toda requisição, além dos de data:

```json
{
  "fetch_config": {
    "mode": "incremental_dates",
    "static_params": {
      "registros_por_pagina": 200,
      "cModulo": "contaspagar"
    },
    "date_dimension": { "..." }
  }
}
```

`static_params` sobrescreve `extra_params` quando há conflito.

---

## 12.9 Construtor de Payload

Para inspecionar o payload que será enviado ao ERP sem executar:

```bash
POST /acme/api/build-payload/
{
  "connection_id": 1,
  "api_definition_id": 2,
  "param_overrides": {
    "pagina": 1,
    "registros_por_pagina": 5
  }
}
```

**Resposta:**

```json
{
  "call": "ListarProdutos",
  "app_key": "***masked***",
  "app_secret": "***masked***",
  "param": [{"pagina": 1, "registros_por_pagina": 5}]
}
```

---

## 12.10 Fluxo Completo — Sincronizar Produtos do Omie

**1. Criar conexão (se ainda não existe):**
```bash
POST /acme/api/connections/
{"provider": 1, "app_key": "...", "app_secret": "..."}
```

**2. Criar job de sincronização:**
```bash
POST /acme/api/sync-jobs/
{
  "connection": 1,
  "api_definition": 3,
  "name": "Produtos Omie"
}
```

**3. Testar com dry run:**
```bash
POST /acme/api/sync-jobs/1/dry_run/
```

**4. Executar sincronização completa:**
```bash
POST /acme/api/sync-jobs/1/run/
```

**5. Verificar resultados:**
```bash
GET /acme/api/sync-runs/?job=1
GET /acme/api/raw-records/?sync_run=1
```

**6. Importar via ETL para produtos:**
```bash
POST /acme/api/etl-import/
{"mapping_id": 1, "data": [...], "commit": true}
```

---

## 12.11 Troubleshooting

| Problema | Causa Provável | Solução |
|----------|---------------|---------|
| `task_id` retorna mas nada é salvo | Celery worker parado | Verificar worker e broker Redis |
| Funciona local, falha em produção | `REDIS_URL` não configurado | Configurar Redis ou usar modo eager |
| `RecordExtractionError` | `transform_config` incorreto | Use dry run, ajuste `records.path` |
| Status `partial` | Erro em segmento intermediário | Verifique `failed_segment_label`, corrija e use `retry/` |
| Erro `consumo redundante` (Omie) | Rate limit da API | Reduza frequência ou page size |
| Registros duplicados | `records.path` incorreto | Desative `autoDiscover`, defina path explícito |
| Credenciais inválidas | `app_key`/`app_secret` errados | Verifique no admin → ERP Connections |

---

## 12.12 Endpoints — Resumo

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{tenant}/api/connections/` | CRUD conexões ERP |
| `GET` | `/{tenant}/api/api-definitions/` | Listar definições de API |
| `GET/POST` | `/{tenant}/api/sync-jobs/` | CRUD jobs de sync |
| `POST` | `/{tenant}/api/sync-jobs/{id}/run/` | Executar sync completo |
| `POST` | `/{tenant}/api/sync-jobs/{id}/dry_run/` | Dry run (teste) |
| `POST` | `/{tenant}/api/sync-jobs/{id}/retry/` | Retry de sync (retoma do cursor) |
| `GET` | `/{tenant}/api/sync-runs/` | Listar execuções |
| `GET` | `/{tenant}/api/raw-records/` | Listar registros brutos |
| `GET` | `/{tenant}/api/raw-records/{id}/data/` | Dados de um registro |
| `POST` | `/{tenant}/api/build-payload/` | Construir payload (teste) |
| `POST` | `/{tenant}/api/etl-import/` | Importar dados via ETL |

---

*Anterior: [11 — Importação ETL](11-etl-importacao.md) · Próximo: [13 — Regras de Automação](13-regras-automacao.md)*

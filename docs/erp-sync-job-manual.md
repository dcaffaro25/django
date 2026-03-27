# ERP Sync Job — In-depth manual

This document describes how **ERP Sync Jobs** work in the Nord Django backend: what they store, how to configure them, how to run them (manually or via workers), and how they relate to **ETL** into business models.

---

## 1. What problem does this solve?

An **ERP Sync Job** (`ERPSyncJob`) ties together:

- Your company’s **credentials** to the ERP (**Omie** today) via `ERPConnection` (`app_key` / `app_secret`).
- A **specific ERP API** to call, described by `ERPAPIDefinition` (URL, method name, parameter schema).

When a job runs successfully, the system:

1. Builds JSON payloads in Omie’s usual shape: `call`, `param`, `app_key`, `app_secret`.
2. Calls the API with **pagination** (`pagina`, `registros_por_pagina`; defaults applied in code if missing).
3. Parses each page, finds the **array of business records** in the JSON (see **transform config** below).
4. Persists **one row per record** in `ERPRawRecord` (raw JSON + pagination metadata + hash).
5. Updates **`ERPSyncRun`** (audit of that execution) and the job’s **last sync** fields.

**Important:** Raw sync **does not** import into `ProductService`, accounting tables, etc. by itself. That is a **separate** step using **ERP API ETL** (`ErpApiEtlMapping` + `POST .../api/etl-import/`). See [Section 10](#10-from-raw-records-to-business-models-etl).

---

## 2. Core concepts and models

| Model | Role |
|--------|------|
| `ERPProvider` | Vendor (e.g. Omie): `slug`, `name`, optional `base_url`. |
| `ERPConnection` | **Per company + provider**: credentials, `is_active`. Unique per `(company, provider)`. |
| `ERPAPIDefinition` | **Global** catalog entry: `call`, `url`, `method`, `param_schema`, optional `transform_config`, `description`. |
| `ERPSyncJob` | **Per company**: links one `connection` + one `api_definition`, `name`, `extra_params`, optional `schedule_rrule`, sync status fields. |
| `ERPSyncRun` | **One execution** of a job: status, page/record counts, `diagnostics`, `errors`, timing, redacted request snapshot. |
| `ERPRawRecord` | **One extracted JSON object** from one API page: `data`, `api_call`, indexes, `page_response_header`, `record_hash`. |

`ERPSyncJob`, `ERPSyncRun`, and tenant-aware helpers extend `TenantAwareBaseModel` and carry a `company` FK. On create via the API, `company` is set from the connection if omitted.

---

## 3. Request payload shape (Omie)

Payloads are built in `erp_integrations/services/payload_builder.py`:

- `call`: from `ERPAPIDefinition.call`.
- `param`: a **list with one object** `[merged]`, where `merged` = defaults from `param_schema` (fields that define `"default"`) **plus** any overrides.
- `app_key` / `app_secret`: from the `ERPConnection`.

**Per-job overrides:** `ERPSyncJob.extra_params` is merged into that single param object. The sync service also ensures pagination keys exist, e.g. `pagina` starting at `1` and `registros_por_pagina` (default `50` in `execute_sync`).

To **inspect** a payload without running a sync, use:

`POST /{tenant}/api/build-payload/`

Body (example):

```json
{
  "connection_id": 1,
  "api_definition_id": 2,
  "param_overrides": { "pagina": 1, "registros_por_pagina": 50 }
}
```

Requires a resolved tenant (see [Section 9](#9-urls-tenants-and-authentication)).

---

## 4. Finding the records array (`transform_config`)

Omie responses are often wrapped or use different key names for the list of rows. Extraction is configured on **`ERPAPIDefinition.transform_config`** (JSON), validated on save. It merges with **defaults** in `erp_integrations/services/transform_engine.py`:

```json
{
  "records": {
    "path": null,
    "fallbackPaths": [],
    "autoDiscover": true,
    "rootAsOneRow": false
  },
  "explode": { "enabled": false, "rules": [], "maxRowsPerItem": 500 },
  "derivedDates": { "rules": [], "inputDateFormat": "dd/MM/yyyy", "inputTimeFormat": "HH:mm:ss" }
}
```

**Practical tips:**

- **`records.path`**: Dot-path to the array, e.g. `produto_servico_cadastro` or nested `data.items`.
- **`fallbackPaths`**: Additional paths to try in order.
- **`autoDiscover`**: If `true`, scans **top-level** keys for the first value that is a **non-empty list of objects** (dicts).
- **`rootAsOneRow`**: If no array is found, wraps the whole object as a single row (rare for list APIs).

If nothing matches, the run fails with `RecordExtractionError` and the error is stored on the sync run.

**Where to edit:** Django **Admin** → ERP API definitions (the public list serializer does not expose `transform_config`; use Admin or direct DB for advanced edits).

---

## 5. Creating an ERP Sync Job

### 5.1 Prerequisites

1. `ERPProvider` exists and is active.
2. `ERPConnection` for **your company** + provider, with valid `app_key` / `app_secret`.
3. `ERPAPIDefinition` for that provider: correct `url`, `call`, and `param_schema` defaults as needed.
4. Optional: set `transform_config` on the API definition if auto-discover fails.

### 5.2 Via REST API

Base path (included under tenant):

`/{tenant}/api/sync-jobs/`

- **List:** `GET .../sync-jobs/`
- **Create:** `POST .../sync-jobs/`

Example body:

```json
{
  "connection": 1,
  "api_definition": 3,
  "name": "Contas a pagar — full sync",
  "is_active": true,
  "extra_params": {
    "pagina": 1,
    "registros_por_pagina": 100
  },
  "schedule_rrule": ""
}
```

`company` is inferred from `connection` when not sent.

### 5.3 Via Django Admin

**Admin** → ERP Sync Jobs: choose connection, API definition, name, `extra_params`, optional `schedule_rrule`.

---

## 6. Running a sync

### 6.1 Full run (persists `ERPRawRecord` rows)

**Endpoint:**

`POST /{tenant}/api/sync-jobs/{id}/run/`

**Behavior:**

- Enqueues Celery task `run_erp_sync_task` → `execute_sync(job_id, dry_run=False)`.
- Response (typical): `{ "task_id": "<celery-uuid>" }`.

**Requirements:**

- **Celery worker** must be running with access to the same broker as the app, **unless** `CELERY_TASK_ALWAYS_EAGER` is enabled (e.g. local dev without Redis — then tasks run in-process).
- If Redis/`REDIS_URL` is unset in settings, the project may run tasks **eagerly**; with Redis in production, workers are **required**.

**Soft/time limits:** `run_erp_sync_task` uses `soft_time_limit=600` / `time_limit=660` seconds (see `erp_integrations/tasks.py`). Very large APIs may need smaller pages or separate jobs.

### 6.2 Dry run (no `ERPRawRecord` rows)

**Endpoint:**

`POST /{tenant}/api/sync-jobs/{id}/dry_run/`

**Behavior:**

- Calls `execute_sync(job_id, dry_run=True)` **inline** (no Celery).
- Processes **page 1 only**; **does not** insert into `ERPRawRecord` (still creates/updates an `ERPSyncRun` and diagnostics).

Use this to verify credentials, URL, and record extraction before a heavy full sync.

### 6.3 Direct Python (operators / debugging)

```python
from erp_integrations.services.omie_sync_service import execute_sync

# Full sync, same as Celery path
execute_sync(job_id=1, dry_run=False)

# Page 1 only, no raw rows
execute_sync(job_id=1, dry_run=True)
```

---

## 7. Pagination and limits

Implemented in `erp_integrations/services/omie_sync_service.py`:

- Loops `pagina` until `pagina >= total_pages` or **max pages** `MAX_PAGES` (200) is reached.
- Default `registros_por_pagina` is set to **50** if not provided in job params.
- **Retries** on Omie “consumo redundante” style rate-limit responses (HTTP 500 with specific fault text), with backoff.

Tune **`extra_params`** on the job for page size and any API-specific filters allowed by Omie.

---

## 8. Scheduled jobs (`schedule_rrule`)

`ERPSyncJob.schedule_rrule` stores an **iCal RRULE** string (example: `FREQ=HOURLY;INTERVAL=6`).

The codebase includes a Celery task `run_all_due_syncs` in `erp_integrations/tasks.py` that selects active jobs with a **non-empty** `schedule_rrule` and dispatches `run_erp_sync_task` for each.

**Operational note:** That task must be **invoked on a schedule** (e.g. Celery Beat entry) in your deployment. The default `CELERY_BEAT_SCHEDULE` in `nord_backend/settings.py` does **not** register `run_all_due_syncs`; add it if you rely on RRULE-based scheduling, or use an external scheduler/cron to call that task.

---

## 9. URLs, tenants, and authentication

### 9.1 Tenant segment

Routes are mounted as:

`/{tenant_id}/api/...`

`tenant_id` is the first path segment. Resolution (see `multitenancy/utils.py` → `resolve_tenant`):

1. By **`Company.subdomain`**, or  
2. If that fails, by **numeric primary key** of `Company`.

Middleware sets `request.tenant` (or `'all'` for superusers on the `all` subdomain).

**Client bug to avoid:** building URLs with a **JavaScript object** instead of a string produces paths like `/[object Object]/api/...`. Use the subdomain string or company id string.

### 9.2 Authentication

DRF defaults include `IsAuthenticated` and token authentication unless your deployment changes it. Call APIs with valid credentials (e.g. `Authorization: Token <key>`).

Custom actions (`run`, `dry_run`) accept the extra URL kwarg `tenant_id` for compatibility with the parent URLconf.

---

## 10. From raw records to business models (ETL)

Raw sync fills **`ERPRawRecord`**. To load into app models (products, etc.):

1. Define **`ErpApiEtlMapping`** (per company): `response_list_key`, `target_model`, `field_mappings`, optional category keys, etc.
2. Call **`POST /{tenant}/api/etl-import/`** with the **full API response JSON** (not only the sync job id), `mapping_id`, and `commit: false` for preview / `true` to commit.

That pipeline reuses the same import machinery as Excel ETL (`execute_import_job`). It is **not** automatically triggered at the end of `execute_sync`; you orchestrate it separately if needed (e.g. after exporting raw JSON or by re-fetching).

---

## 11. Observing results

### 11.1 REST

| Endpoint | Purpose |
|----------|---------|
| `GET /{tenant}/api/sync-runs/?job=<job_id>` | List runs for a job. |
| `GET /{tenant}/api/raw-records/?sync_run=<run_id>` | Raw rows for a run. |
| `GET /{tenant}/api/raw-records/?api_call=<CallName>` | Filter by Omie `call` name. |

Serializers expose counts, `diagnostics`, `errors`, timing; they do **not** expose `request_payload_redacted` — use **Django Admin** on `ERPSyncRun` for the redacted payload snapshot if needed.

### 11.2 Job status fields

On `ERPSyncJob`: `last_synced_at`, `last_sync_status` (`never`, `completed`, `failed`, `partial`, `running`), `last_sync_record_count`.

### 11.3 Admin

Inspect **ERP Sync Jobs**, **ERP Sync Runs**, and **ERP raw records**; useful for operators who need full JSON and redacted requests.

---

## 12. Troubleshooting

| Symptom | Things to check |
|--------|-------------------|
| `task_id` returned but nothing stored | Celery worker down; broker misconfigured; task failed — check worker logs and `ERPSyncRun.errors`. |
| Works locally, not in production | `REDIS_URL` / eager vs async; firewall to Omie; credentials. |
| `RecordExtractionError` | `transform_config` / path; use **dry_run** and inspect `diagnostics`. |
| `consumo redundante` / 500 | Retries exist; reduce frequency or page size. |
| Duplicate or huge rows | Confirm correct `records.path`; turn off `autoDiscover` if it picks the wrong array. |
| TypeError on `tenant_id` | Ensure backend includes handlers that accept `tenant_id` on tenant-prefixed routes (fixed in `ERPSyncJobViewSet.run` / `dry_run`). |

---

## 13. Quick reference — endpoints under `erp_integrations`

All prefixed by `/{tenant}/` (and your host):

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `api/connections/` | CRUD ERP connections. |
| GET | `api/api-definitions/` | List/read API definitions (`?provider=` optional). |
| GET/POST | `api/sync-jobs/` | CRUD sync jobs. |
| POST | `api/sync-jobs/{id}/run/` | Queue full sync (Celery). |
| POST | `api/sync-jobs/{id}/dry_run/` | Page 1, no raw inserts. |
| GET | `api/sync-runs/` | List runs (`?job=`). |
| GET | `api/raw-records/` | List raw records (`?sync_run=`, `?api_call=`). |
| POST | `api/build-payload/` | Build request JSON for testing. |
| POST | `api/etl-import/` | ETL preview/commit from a response + mapping. |

---

## 14. Related files (for developers)

- `erp_integrations/models.py` — schema.
- `erp_integrations/views.py` — viewsets and actions.
- `erp_integrations/urls.py` — routes (`api/` include).
- `erp_integrations/services/omie_sync_service.py` — HTTP loop, storage, dry run.
- `erp_integrations/services/payload_builder.py` — payload construction.
- `erp_integrations/services/transform_engine.py` — record extraction and config validation.
- `erp_integrations/tasks.py` — Celery tasks.
- `erp_integrations/erp_etl.py` — ERP response → import job for ETL.

---

*Last updated to match the codebase layout and behavior as of the manual’s authoring date. If you add Beat entries or change serializers, update this document accordingly.*

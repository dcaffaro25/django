# Imports v2 — Implementation Plan

Handover document for the v2 interactive-import feature (analyze →
resolve → commit, with `SubstitutionRule` auto-creation). Legacy
bulk-import (`/api/core/bulk-import/`) and legacy ETL
(`/api/core/etl/preview|execute|analyze/`) stay untouched throughout.

Read this once when resuming on a new machine, then the numbered
Phase sections for the specific next step.

---

## 1. Status summary

Backend phases 1–4B, frontend phases 5–6, and ops/reliability phase
6.z-h are all shipped to `main`. Full v2 backend suite: **122 tests
green** (last measured 2026-04-23; post-6.z-h the frontend tests grew
but the backend-only count is unchanged).

v2 is feature-complete end-to-end for both template and ETL paths
and running on Railway prod with Celery Beat + stale-session reaper
live. Remaining work is Phase 7 cleanup (**gated on production
burn-in**) + the B1–B4 backend backlog (optional follow-ups).

| Ref         | What shipped                                                                 |
|-------------|------------------------------------------------------------------------------|
| `adf732d`   | Pure grouping helper `_group_transaction_rows_by_erp_id` + 13 unit tests     |
| `ff9e664`   | Manual §11.10c — erp_id grouping semantics for Transaction imports (pt-BR)   |
| `6882a25`   | Phase 1 — `ImportSession` model + `SubstitutionRule.source` field + tests    |
| `8c56913`   | Phase 2 — Template v2 backend (analyze + commit) + 14 tests                  |
| `0cc9835`   | Phase 3 — ETL v2 backend (analyze + commit) + 9 tests                        |
| `b82ab4e`   | Phase 3.6 — Engine perf (pre-compile) + `skip_substitutions` hint + 25 tests |
| `0bb9332`   | Phase 4A — Resolve endpoint + pick/skip/ignore/abort + staged-rule commit    |
| `d547670`   | Phase 4B — bad_date/negative/unmatched detectors + map/edit handlers + 24 t  |
| `8d44dd4`   | Phase 5 — Template v2 frontend (toggle + DiagnosticsPanel + 6 issue cards)   |
| `f253e0f`   | Phase 6 — ETL v2 frontend + ErpIdGroupsSection + serializer.transaction_groups |
| `1951ff6`   | Phase 6.x — Rule picker dropdown + ETL preview passthrough + AnalyzePreviewPanel |
| `8a2e8d9`   | Phase 6.y — Template dry-run at analyze (≤5k rows auto; would_create/update/fail) |
| `6bf433e`   | Phase 6.z-a — Async analyze + commit via Celery (backend + frontend polling) |
| `c06a013`   | Phase 6.z-b + 6.z-c — Queue panel + sidebar badge + session detail + deep-link |
| `1863041`   | Phase 6.z-d/e/f — Sub-cache reuse, live progress, LookupCache perf, stale-session reaper |
| `789e82e`   | Phase 6.z-g — Intra-atomic row-level progress via Redis channel |
| `c58de9c`   | Phase 6.z-h — Celery Beat service + reliability knobs + email retry + queue diagnostics |
| `ce39344`   | Ops hotfix — restore production worker startCommand after railway.json drift |
| `73e9cbf`   | Ops hotfix #2 — restore production web startCommand + railway.json safety checklist |
| `8a07ace`   | Admin — runtime config inspection (CLI + HTTP endpoint + /admin/runtime page) |
| `5bfd606`   | Auth fix — `/api/auth/me/` endpoint so SuperuserGuard actually works |
| `96e796c`   | Admin UX — platform-admin links moved from sidebar to user dropdown |
| `e651918`   | Admin — RuntimePage renderer polish (total_tasks dict, uptime, prefetch label) |
| `296735f`   | Ops — strip unused `workloads[]` from railway.json + correct the docs (head of main) |

**Resolved follow-up — template dry-run.** Phase 6.y shipped the
missing piece: template analyze now runs `execute_import_job(commit=False)`
when the total row count is under `TEMPLATE_DRY_RUN_ROW_THRESHOLD`
(5000), tallies per-model create/update/fail counts, and stashes
them on `parsed_payload["preview"]`. The `AnalyzePreviewPanel` now
lights up for both modes. Above the threshold the dry-run is
skipped (would double analyze cost on huge imports); operators still
see sheet-level counts + full diagnostics, just not the bottom-line
tallies. An explicit "Ver prévia detalhada" button for big files is
the obvious next iteration if anyone asks for it.

**Phase 6.z-a — async analyze + commit (backend).** Both analyze and
commit are now handed off to Celery via `.delay()` so gunicorn's 300s
timeout can't bite on 3-5k-row imports. Split architecture:

  * `services._create_template_session` / `_create_etl_session` — persist
    the session row in `analyzing` state with `file_bytes` + `config`
    inlined, so the worker has everything it needs from just the pk.
  * `services._run_analyze_template` / `_run_analyze_etl` / `_run_commit` —
    the heavy bodies, moved out of the top-level public functions and
    callable from either the sync entry point or a Celery worker.
  * `services.analyze_template_async` / `analyze_etl_async` /
    `commit_session_async` — create/flip + enqueue + `refresh_from_db`.
    Views use these.
  * `multitenancy/imports_v2/tasks.py` — `@shared_task analyze_session_task`
    + `commit_session_task`. Both bail out if the session left the
    non-terminal state (dedup on retry) and flip to `error` on
    unhandled exceptions.

Views return **202 Accepted** now (not 201/200). In eager mode
(`REDIS_URL` unset — tests + dev) `.delay()` runs inline so the
returned session is already terminal; production goes through the
broker and the frontend polls `GET /sessions/<id>/` until status
leaves `analyzing`/`committing`. The existing 19 regression tests
plus 8 new `V2AsyncTaskTests` cover task-level edge cases (missing
pk, status-gating, error translation, mode dispatch). Frontend
polling hook ships in 6.z-b.

**Phase 6.z-b — queue panel + sidebar badge.** The Imports hub page
now renders a live queue panel below the upload tabs showing the
last N sessions for the current tenant. Two new backend endpoints
back it:

  * `GET /api/core/imports/v2/sessions/` — paginated lightweight list
    (`ImportSessionListSerializer` — no `parsed_payload`/`open_issues`
    /`result` in the payload so a queue of 25 stays tiny). Filters:
    `?status=analyzing,committing` (comma-separated whitelist),
    `?mode=template|etl`, `?page_size=N` (≤100).
  * `GET /api/core/imports/v2/sessions/running-count/` — single
    `GROUP BY status` aggregate for the sidebar badge. Returns
    `{analyzing, committing, awaiting_resolve, total}`.

Frontend pieces:

  * `useImportSessionsList` — TanStack Query hook with dynamic
    refetch interval (3s while any row is running; 15s when all
    terminal).
  * `useRunningImportCount` — polls every 10s globally; pauses when
    the tab is backgrounded.
  * `ImportQueuePanel` — table with status chip, relative timestamp,
    operator name, issue count. Rows are clickable (wired for 6.z-c).
  * `ImportsRunningBadge` — sidebar pill next to "Importar arquivos"
    and "Templates". Red dot when `awaiting_resolve > 0`, amber
    otherwise. Collapsed sidebar shows a dot on the icon instead of
    the number.

9 new tests in `V2SessionsListEndpointTests` cover tenant scoping,
filter parsing, ordering, the lightweight payload shape, and the
bucketed count. All green.

**Phase 6.z-c — inline session-detail view.** Clicking a queue row
expands it into a read-only `SessionDetailView` rendered below the
queue:

  * Auto-refetches every 2s while the session is non-terminal so an
    operator opening a mid-run session sees progress live.
  * Reuses the existing `DiagnosticsPanel` (showing the worker-busy
    state for in-flight sessions, diagnostics for awaiting_resolve,
    results for committed).
  * Adds a `Resultado bruto (JSON)` collapsible for troubleshooting.
  * Close button clears the URL query param.

Deep-linking via `?tab=<tab>&session=<id>` — operators can share the
URL of an import in triage. Garbage values (non-numeric) are
ignored so a malformed link doesn't crash the page.

**6.z-c update — queue is now fully interactive.** The follow-up
lift landed: `useSessionActions(sessionPk, session)` hook
encapsulates resolve + commit + polling + cache invalidation, and
`SessionDetailView` passes both callbacks to `DiagnosticsPanel`.
Operators can now drive the full flow from the queue without
leaving the hub.

**Phase 6.z-d — substitution cache reuse at commit.** Analyze now
pre-substitutes each sheet once and stashes the result in
`parsed_payload["sheets_post_substitution"]` along with a
fingerprint of the active `SubstitutionRule` set
(`substitution_revision`). At commit, `_commit_template_session`
checks the invariant (hash matches + no resolutions recorded
since) and, when valid, reuses the cached rows while passing a new
`import_options.skip_substitutions` flag to `execute_import_job`
so the pipeline skips the second pass. Idempotent by construction:
`apply_substitutions` matches against `match_value` not the
substituted value, so even if the cache check misses a staleness
signal the output is still correct (we just paid for a redundant
pass). 6 new tests cover the hash stability, tenant scoping, and
the cache-valid predicate.

**Phase 6.z-e — live progress feedback.** Adds
`ImportSession.progress` (migration 0037) — a JSON snapshot the
worker writes at stage boundaries so the polling frontend can
render a live "Analisando…" / "Escrevendo no banco…" strip with
percentage + error count.

Analyze gets genuine real-time progress — detectors loop outside
any atomic block so per-sheet writes stream through
(`sheets_done` / `sheets_total` update live). Commit gets
coarser "starting write → done" because the write loop runs
inside `transaction.atomic()` — any `session.save` from inside
isn't visible to the polling frontend until the block commits.
Intra-commit row-level progress needs a separate DB connection
or Redis progress store (future iteration); the panel strip is
honest about this and shows an indeterminate spinner for the
write phase.

Frontend `ProgressStrip` component renders two variants: `card`
(DiagnosticsPanel header) and `inline` (per queue row, next to
the status chip). Reads `session.progress.stage` for the label,
`sheets_done/sheets_total` for the bar, `errors_so_far` for the
amber badge.

**Phase 6.z-f — perf fix + stale-session reaper.** Diagnosing a
report of "3.5k rows taking 10+ min" exposed two interacting bugs:

1. **`LookupCache` was never wired into v2** (`_template_dry_run_preview`
   + `_commit_template_session` called `execute_import_job` without
   `lookup_cache=...`). ETL mode had been doing this since day one via
   `ETLPipelineService.__init__`. Every FK reference in every row
   was hitting the DB — thousands of extra round-trips to Railway's
   remote Postgres (10-50ms each). **Fixed**: v2 now instantiates
   `LookupCache(company_id)` + `.load()` before both dry-run and
   commit, mirroring the ETL pattern.

2. **Celery hard time-limit was 10 min, labeled 15.** Settings said
   `CELERY_TASK_TIME_LIMIT = T_LIMIT*60  # 15 minutes` but the
   math produced 600s (10 min) on the default `T_LIMIT=10`. A commit
   that took >10 min got SIGKILL'd by Celery without the exception
   handler running, leaving the session stuck in `committing`
   forever. **Fixed**: default raised to 30 min (`T_LIMIT=30`),
   comments rewritten to match the actual seconds value.

3. **No safety net for stuck sessions.** Even with the two fixes
   above, a worker SIGKILL / container restart / broker loss could
   still leave a session orphaned. **Fixed**: new
   `reap_stale_sessions_task` Celery beat task runs every 5 min
   and flips sessions in `analyzing`/`committing` past the hard
   limit + 60s grace to `error` with a timeout diagnostic.
   `SoftTimeLimitExceeded` handlers in `analyze_session_task` +
   `commit_session_task` also flip to error pre-kill on genuine
   runaways.

4 new tests in `V2StaleSessionReaperTests` cover the reaper's
happy paths (analyzing + committing) plus the two negative cases
(fresh sessions must not be touched; terminal sessions must not
be re-reaped).

**Phase 6.z-g — intra-atomic row-level progress via Redis.** Closes
the gap 6.z-e was honest about. The problem: the commit write loop
runs inside `transaction.atomic()`, so any `session.save` from
within is invisible to the polling frontend until the block
commits. 6.z-e gave us stage-level progress at the boundaries; 6.z-g
publishes row-level progress during the write via Redis (which
is already in the stack as the Celery broker).

Architecture (dual channel):

  * `ImportSession.progress` JSONField — durable DB snapshot, written
    at stage boundaries outside the atomic block. Canonical post-commit.
  * Redis `imports_v2:progress:<session_pk>` — live channel, written
    every 100 rows during the write loop. Bypasses the DB transaction
    entirely. TTL = `CELERY_TASK_TIME_LIMIT + 120s`; explicit
    `progress_channel.clear(pk)` from the Celery task's `finally` block
    on terminal.

Plumbing:

  * `execute_import_job(progress_callback=...)` — new optional kwarg.
    Fires at every sheet start + every `PROGRESS_ROW_INTERVAL` (100)
    rows during the per-row loop. Throttled by modulo so a 10k-row
    file generates ~100 writes instead of 10k. Callback errors are
    swallowed — progress publishing can never block the import.
  * `multitenancy/imports_v2/progress_channel.py` — lazy-imported
    `redis` client, `publish(pk, fields)` merges into the existing
    blob and bumps `updated_at`, `read(pk)` returns the current
    snapshot or None, `clear(pk)` deletes the key. Degrades to
    no-ops when `REDIS_URL` is absent (tests + dev), so the stack
    keeps working without a broker.
  * `services._commit_template_session` creates a closure
    `_on_progress(fields)` that publishes to Redis with
    `stage="writing"`; passes it via `progress_callback`.
  * `ImportSessionSerializer.get_progress` (and the list variant)
    merge: for non-terminal sessions, Redis fields override DB
    fields (Redis is fresher for row-level work); for terminal
    sessions, read DB only (Redis might still have a stale key for
    a few seconds while the clear propagates).

Frontend `ProgressStrip` prefers row-level data when available:

  * `rows_processed / rows_total` → real percentage bar, "Transaction
    · 1.847 / 5.000 linhas" caption.
  * Falls back to `sheets_done / sheets_total` from the DB snapshot.
  * Falls back to an indeterminate spinner when neither is present.

10 new tests cover:

  * `V2ProgressCallbackTests` — sheet-boundary firing, 100-row
    throttling, callback errors don't block import.
  * `V2ProgressSerializerMergeTests` — non-terminal prefers Redis,
    falls back to DB when Redis empty, terminal ignores Redis
    entirely (doesn't even call `read`).
  * `V2ProgressChannelTests` — the module itself degrades cleanly
    when `REDIS_URL` is absent (all three verbs no-op).

**Phase 6.z-h — Celery Beat + reliability knobs + diagnostics.**
Audit triggered by a "tasks are stuck" report uncovered four
production issues that all compound:

  1. **Celery Beat was never deployed.** `railway.json` had only
     `web` + `worker` — no `beat`. Every periodic task in the
     `CELERY_BEAT_SCHEDULE` (including the stale-session reaper
     shipped in 6.z-f) was a paper tiger. **Fixed:** added a third
     Railway workload running `celery -A nord_backend beat`. See
     §X.x below for the wiring walkthrough.
  2. **`broker_connection_retry_on_startup`** was declared as a
     free-floating module variable at the top of `celery.py` —
     never actually applied to `app.conf`. Workers crashed on
     startup if Redis had a transient hiccup. **Fixed:** moved
     into `app.conf.update(...)`.
  3. **Default `acks_late=False` + `task_reject_on_worker_lost=False`**
     meant tasks SIGKILL'd by Railway container restarts or OOM
     were silently lost (not re-queued). That's what "stuck" looked
     like to the operator — the queue empties but the session
     polling never finishes. **Fixed:** both set to `True` in
     `celery.py`. Imports v2 tasks are idempotent (status-gated),
     so re-run is safe.
  4. **`worker_prefetch_multiplier` default = 4** on a 2-worker
     concurrency meant up to 8 tasks were reserved but not
     executing. **Fixed:** set to 1 for fair scheduling. Plus
     `worker_max_tasks_per_child = 200` to contain memory leaks
     from pandas/numpy caches across ETL imports.

Also tightened `send_user_email` retry policy: bare
`autoretry_for=(Exception,)` retried 5 times with backoff on a
permanent auth error, tying up workers for 30+ min per bad email
during an SMTP outage. Now narrowed to transient exceptions
(SMTP temp failures, TCP resets) with `max_retries=3` and hard
`time_limit=120s`.

Two new management commands for ops:

  * `python manage.py celery_queue_stats` — read-only snapshot of
    Redis queue depth, active/reserved/scheduled tasks per worker,
    and count of stuck v2 ImportSessions. `--json` for tooling.
  * `python manage.py celery_purge_stuck` — emergency tool. Can
    (a) purge a Redis queue, (b) revoke+terminate active tasks,
    (c) run the stale-session reaper synchronously. Always
    `--dry-run` first.

## Railway Beat service — step-by-step wiring

When this change deploys, Railway will automatically create the
new ``beat`` workload from `railway.json`. For the first time
**only** (or if you want to verify it's up), follow this sequence:

1. **Push the commit containing the updated `railway.json`** to
   `main`. Railway auto-detects the new `workloads[]` entry and
   starts the service on the next deploy.

2. **Open the Railway dashboard** → the project → the service
   tab. You should see three services: `web`, `worker`, `beat`.
   If `beat` is missing, the schema parse failed — check the
   deploy logs for a JSON error.

3. **Click `beat` → Settings → Environment.** Verify it has the
   same `REDIS_URL` as `worker` and `web`. The broker URL is the
   most critical variable; a mismatch means Beat queues tasks
   onto one Redis while workers pick up from another. If you use
   Railway's Redis plugin via reference variables, this should
   automatically cascade from the same source.

4. **Check replicas.** Beat MUST be a single instance —
   replicas=1, no autoscale, no restart-storm behaviour. Two
   Beat processes would fire every periodic task twice (every
   embedding backfill, every reaper tick, every weekly digest).
   Railway default for custom workloads is 1 replica, but if
   you've enabled autoscale for any reason, disable it for
   `beat`.

5. **Inspect the logs.** Click `beat` → Logs. You should see
   lines like:
   ```
   [INFO/MainProcess] beat: Starting...
   [INFO/MainProcess] Scheduler: Sending due task imports-v2-reap-stale-sessions
   [INFO/MainProcess] Scheduler: Sending due task erp-sync-scheduled-jobs
   ```
   If you only see "Starting..." and then silence, the scheduler
   loaded but no tasks are due yet — that's fine. Wait up to
   5 minutes (our shortest period) to see the first tick.

6. **Verify from the app side.** Open a session stuck in
   `committing` for >35 min. Within 5 minutes of Beat's first
   reaper tick, its status should flip to `error` with
   `result.stage == "timeout"`. You can also run
   `python manage.py celery_queue_stats` from a Railway shell and
   watch `stale_import_sessions.count` drop.

7. **If Beat dies / the container restarts:** the `--schedule=/tmp/celerybeat-schedule`
   path is ephemeral. That's intentional for simplicity — Beat
   reads `CELERY_BEAT_SCHEDULE` from Django settings on every
   boot, so we don't need to persist the file across restarts.
   The only cost is that a long-delayed one-off task (if we ever
   add one) would re-fire on restart, which is fine for the
   current schedule of crontab-pattern periodic tasks.

Upgrade path: if the schedule becomes too dynamic to live in
`settings.py` (e.g. per-tenant schedules set via admin UI), add
`django-celery-beat` with the `DatabaseScheduler` and migrate the
definitions into a model. No code changes required on the
producer/consumer side.

## Railway wiring — what this repo actually controls

**Corrected on 2026-04-24 after a false alarm.** Our Railway project
runs three services from this repo — `Main Server` (gunicorn),
`Celery` (worker), `Beat` (beat scheduler, added Phase 6.z-h) —
each as a separate Railway service with its own `startCommand` set
**in the dashboard**, NOT in `railway.json`.

That means:

- `railway.json` in this repo only declares the **builder** (Railpack)
  and shared build hints. It does NOT carry `startCommand` values.
- Editing `railway.json` never changes what any service runs.
- If someone tries to add a `deploy.workloads[]` block, Railway
  ignores it for our multi-service setup. The workloads schema is
  for single-service multi-process deployments — not us.

**The authoritative source for each service's start command is the
Railway dashboard.** To verify or change what a service runs:
Services → `<service>` → Settings → Deploy → Start Command.

### Current production start commands (2026-04-24)

Recorded here for reference only. Any change must happen in the
Railway dashboard; this file just documents what's there.

**Main Server** (web):
```
python -u manage.py migrate
  && python -u manage.py ensure_superuser
  && python -u manage.py collectstatic --noinput
  && gunicorn nord_backend.wsgi:application
    --bind 0.0.0.0:$PORT
    --access-logfile - --error-logfile -
    --log-level info --capture-output
    --timeout 600 --keep-alive 30
    --workers 2 --worker-class gthread --threads 4
    --max-requests 500 --max-requests-jitter 50
```
Key invariants: `python -u` (unbuffered logs), `--bind 0.0.0.0:$PORT`
(Railway injects `$PORT`), `gthread` worker class + `--threads 4`
(8 concurrent requests with 2 workers), `--max-requests 500`
(worker recycles before memory bloats).

**Celery** (worker):
```
celery -A nord_backend worker --loglevel=INFO
  -Q celery,recon_legacy,recon_fast
  --autoscale=20,4
  -Ofair
  --prefetch-multiplier=1
```
Key invariants: multi-queue consumption (don't drop any of the
three), autoscale 4-20, fair scheduling. The CLI `--prefetch-multiplier=1`
matches the config-level `worker_prefetch_multiplier=1` in
`nord_backend/celery.py`.

**Beat** (scheduler, added Phase 6.z-h):
```
celery -A nord_backend beat --loglevel=INFO --schedule=/tmp/celerybeat-schedule
```
Key invariants: **single replica only** (two Beats = every scheduled
task fires twice), no health check (doesn't listen on a port),
`--schedule=/tmp/celerybeat-schedule` is fine as ephemeral state
because all our schedules are crontab-based (see "Where does the
Beat schedule live?" below for the full explanation).

### If a service's command needs to change

1. Open Railway dashboard → `<service>` → Settings → Deploy.
2. Take a screenshot of the current Start Command before editing.
3. Change it, redeploy, and watch the service's logs for the first
   minute to confirm the expected flags loaded (gunicorn prints its
   worker/thread config; Celery prints its queue subscription).
4. Update the "Current production start commands" section above
   so the next person looking here sees the current truth.

### Source of the earlier hotfix scare

I'd assumed `railway.json` `workloads[]` drove the startCommands
and committed replacements that DIDN'T match what the dashboard
had. Two back-to-back hotfixes chased the drift (restoring the
real commands). If Railway's `workloads[]` feature does apply to
our setup in some future evolution, we can reintroduce it
deliberately then — with the dashboard values copied into the
file verbatim first.

Nothing uncommitted on main. When resuming on a new machine:

1. `git pull` on `main`.
2. Apply migrations against any local/homolog DB (`0037_importsession_progress` is the latest).
3. Run the v2 test suite (command below) — expect ~122 green on the
   seven v2 backend modules combined. Full project suite is larger.
4. Pick one of:
   - **Phase 7** — legacy split-delete removal. **Gated**: requires at
     least one month of production burn-in where v2 is the dominant
     import path. Check prod metrics (sessions created per week,
     % of imports hitting v2 vs legacy) before merging.
   - **Backend backlog** — B1 (`je_balance_mismatch` detector), B2
     (extend `_REFERENCE_FIELD_LOOKUPS`), B3 (`update_staged_rule`
     action), B4 (Celery TTL sweep). B4 partially superseded by the
     stale-session reaper in 6.z-f — re-assess scope before starting.
   - **Ops** — any observed prod issue from the 6.z-h queue
     diagnostics (`python manage.py celery_queue_stats`) or from
     `/admin/runtime` inspection.

### Production DB unblocked (2026-04-23)

A partial apply of `0035_v2_import_session` left three stray indexes on
the Railway `switchback:17976` DB without `0035` being recorded in
`django_migrations` — see `.claude/diag_0035.py` + `.claude/fix_0035.py`
in this worktree for the exact runbook we ran. Both 0035 and 0036 are
now applied and recorded on prod. If a future partial-apply happens,
re-use the same diag+fix pattern.

### Tests pass live on these paths

Both modes work end-to-end for clean files (no issues → READY →
commit). Files with blocking issues land in `awaiting_resolve`;
Phase 4 resolve endpoint now advances them to `ready` (or `error`
on abort).

### Run the full v2 test suite

```bash
DJANGO_SETTINGS_MODULE=nord_backend.settings \
  python -m pytest \
    multitenancy/tests/test_transaction_erp_id_grouping.py \
    multitenancy/tests/test_import_session_model.py \
    multitenancy/tests/test_imports_v2_backend.py \
    multitenancy/tests/test_imports_v2_etl.py \
    multitenancy/tests/test_substitution_engine_perf.py \
    multitenancy/tests/test_imports_v2_resolve.py \
    multitenancy/tests/test_imports_v2_phase4b.py \
    -v --reuse-db
```

First run with `--create-db` takes ~9 min on Windows (big project,
many migrations). Second run with `--reuse-db` is ~2–3 min.

---

## 2. Remaining work

Listed in execution order. Each phase is independently reviewable
and mergeable.

### Phase 3.6 — Engine perf + per-column "skip substitutions" hint ✅ SHIPPED

Shipped together with this plan revision. Summary of what actually
landed:

- `formula_engine._make_filter_fn` pre-walks the `filter_conditions`
  JSON tree into a closure once per rule (all/any/not/leaf ops).
- `formula_engine._build_compiled_rule_meta` attaches pre-compiled
  regex / pre-normalized caseless match_value / pre-parsed filter
  closure to each rule, keyed by `id(rule)`.
- Hot loop uses `_apply_compiled_rule` — no re-compile/re-normalize
  per row.
- Dead `column_name` / `column_index` rule-grouping branches removed
  (fields gone since migration 0023); `column_names` kwarg kept as
  a legacy no-op for backward compat; `apply_substitutions2` deleted
  (dead helper, would've AttributeError'd on first call).
- `apply_substitutions(skip_fields=..., stats_out=...)` — new kwargs.
  `skip_fields` zeroes rule lookups on flagged target-field names
  (verified via `stats_out['rule_hits']`). Honours both the FK
  substitution phase and the model-field phase.
- `ImportTransformationRule.column_options` JSONField + migration
  `0036_importtransformationrule_column_options`. Shape:
  `{"amount": {"skip_substitutions": true}}`.
- `ETLPipelineService._extract_skip_substitution_fields` converts the
  column_options dict into a set of target-field names; wired into
  `_apply_substitutions` (FK phase + model phase) and the
  transaction-pre-analysis call at
  `etl_service.py:_import_transactions_with_journal_entries`.
- 25 tests in
  `multitenancy/tests/test_substitution_engine_perf.py` — covers
  compiled filter closure ops, regex pre-compile, caseless
  pre-normalize, stats_out contract, skip_fields bypass (verified
  via `rule_hits` counter, not just unchanged values), and the
  `_extract_skip_substitution_fields` helper.

**Known non-goal carried forward:** the per-value substitution cache
is populated on first successful substitution and reused for later
rows with the same value regardless of filter_conditions. This is
unchanged pre-existing behaviour and not in Phase 3.6's scope.
Documented in the affected test's docstring.

---

### Phase 3.6 — Engine perf + per-column "skip substitutions" hint (historical design notes)

**Why** — the existing substitution engine at
`multitenancy/formula_engine.py:apply_substitutions()` (line 602)
already has per-value memoization and pre-grouped rules by
`(model_name, field_name)`, but three hot spots remain:

1. Regex patterns compiled per row (lines 743, 796) — no `re.compile`
   cache
2. `_normalize(match_value)` (caseless + accents via NFKD + casefold,
   line 541) runs per call, not per rule
3. `filter_conditions` JSONField walked recursively per row per rule

**Deliverables**:

- Pre-compile regex patterns once at cache-build time and attach the
  compiled pattern to the in-memory rule.
- Pre-normalize the caseless `match_value` once per rule at
  cache-build time.
- Parse `filter_conditions` JSON into a Python closure once per rule.
- Remove dead `column_name` / `column_index` iteration branches
  (fields were removed in migration 0023).
- Add a per-column `skip_substitutions: bool` hint to
  `ImportTransformationRule.column_mappings` (new JSON field or add
  a parallel `column_options` dict). Default OFF.
  - Engine respects it: zero rule lookups on flagged columns.
  - Migration adds the field; existing rows default to empty dict
    (no behaviour change).

**Tests**:

- Regex rule fires correctly after pre-compile (doesn't become a
  static string).
- Caseless rule fires correctly with pre-normalized match_value
  (accent-sensitivity baseline preserved).
- Skip hint: column flagged `skip_substitutions=true` never hits
  the rule cache (assert via cache-hit counter).
- Profiler output still reports per-rule times correctly.

**Scope estimate**: ~200 LoC + ~150 LoC tests. One commit to main.

---

### Phase 4A — Resolve endpoint skeleton + staged-rule commit ✅ SHIPPED

Shipped with this plan revision. Unblocks awaiting-resolve sessions
for the conflict detectors that already exist (``erp_id_conflict``,
``missing_etl_parameter``). Summary of what landed:

- ``multitenancy/imports_v2/resolve_handlers.py`` — per-action
  handlers for ``pick_row``, ``skip_group``, ``ignore_row``, ``abort``.
  Handlers mutate ``session.parsed_payload`` in-place (template mode's
  ``sheets`` dict or ETL mode's ``transformed_data`` dict — abstracted
  via ``_rows_container``). ``apply_resolution`` dispatches on action
  and gates via the issue's ``proposed_actions`` whitelist.
- ``services.resolve_session(session, resolutions)`` — orchestrator.
  Validates the session is non-terminal + non-committing, walks the
  batch applying each resolution, appends to ``session.resolutions``,
  re-detects issues against the mutated payload, and flips status to
  ``ready`` if no blocking issues remain. ``abort`` short-circuits the
  batch and flips to ``error``.
- ``ResolveSessionView`` (both URL namespaces) at
  ``POST /api/core/imports/v2/resolve/<pk>/`` and
  ``POST /api/core/etl/v2/resolve/<pk>/``.
- ``commit_session`` now materialises ``session.staged_substitution_rules``
  into real ``SubstitutionRule`` rows with ``source=import_session``
  + ``source_session=FK`` inside the commit's outer atomic block;
  created pks are returned in the response as
  ``result.substitution_rules_created``.
- 28 new tests in
  ``multitenancy/tests/test_imports_v2_resolve.py``: handler units
  (happy + guardrails), ``resolve_session`` service (happy, abort,
  partial, terminal, committing, unknown issue_id, malformed batch),
  view (400/404/409/200), commit materialisation (creates real rows,
  rollback on malformed entries, empty staged list → empty pks), and
  a full analyze→resolve→commit integration test.

**Phase 4B shipped (this commit):**

- Detectors: ``bad_date_format`` (ISO + pt-BR DD/MM/YYYY parsing on
  common date columns); ``negative_amount`` (driven by
  ``ImportTransformationRule.column_options[field]['positive_only']``);
  ``unmatched_reference`` + ``fk_ambiguous`` (tenant-scoped name lookups —
  currently just ``entity → Entity.name``, extensible via
  ``_REFERENCE_FIELD_LOOKUPS``).
- Handler ``edit_value`` (for bad_date_format / negative_amount).
- Handler ``map_to_existing`` (for unmatched_reference / fk_ambiguous) —
  rewrites payload rows AND optionally appends a ``SubstitutionRule``
  spec to ``session.staged_substitution_rules`` so commit materialises
  it. Requires ``issue.context.related_model`` (detectors populate it).
- ``resolve_session`` now persists ``staged_substitution_rules`` too
  (the 4A save forgot that field).
- 24 new tests in ``test_imports_v2_phase4b.py``: ``_tryparse_date``
  unit, each detector's happy + edge cases, each handler's happy +
  guardrails, and a map → commit integration test that verifies the
  staged rule materialises with the right ``source=import_session``
  FK and ``match_value``/``substitution_value``.

**Known caveats / deferred (backend backlog — do one at a time):**

- **B1. ``je_balance_mismatch`` detector.** Needs a discriminator
  tying JournalEntry rows to their parent Transaction (via
  ``transaction_erp_id`` or similar) before the Σdebit vs Σcredit
  check can land confidently. Template mode: group by the JE sheet's
  transaction-key column; ETL mode: group by the combined Tx+autoJE
  rows. Proposed actions on the issue: abort, ignore_row,
  edit_value. Scope: ~80 LoC + ~100 tests.
- **B2. Extend ``_REFERENCE_FIELD_LOOKUPS``** — add `account_path →
  Account.path-ish-lookup`, `cost_center → CostCenter.name`,
  `bank_account → BankAccount.name`. First one unblocks a real
  ``fk_ambiguous`` test (Account.name isn't unique per company).
  Scope: ~60 LoC + ~60 tests.
- **B3. ``update_staged_rule`` action** — lets the operator tweak a
  staged rule (match_type, match_value) before commit without having
  to re-map-to-existing. Params: ``{index, rule: {...}}``. Scope:
  ~40 LoC + ~40 tests.
- **B4. Celery cleanup beat** for expired sessions. Model already
  has ``expires_at``; just needs a periodic task that deletes /
  clears file_bytes on anything past TTL. Scope: ~30 LoC + one task
  registration.

---

### Phase 4 — Resolve endpoint + `SubstitutionRule` auto-creation (historical design notes)

The big one. Unlocks awaiting-resolve sessions for both modes.

**Deliverables**:

1. **New endpoint** `POST /api/core/imports/v2/resolve/<session_id>/`
   (and the `/api/core/etl/v2/resolve/<session_id>/` mirror using the
   same view). Accepts:

   ```json
   {
     "resolutions": [
       {
         "issue_id": "iss-abc123",
         "action": "pick_row" | "skip_group" | "abort"
                 | "map_to_existing" | "edit_value" | "ignore_row",
         "params": { ... per-action shape ... }
       }
     ]
   }
   ```

   Returns the updated session with `open_issues` mutated,
   `resolutions` appended, `staged_substitution_rules` possibly
   populated, and `status` advanced to `ready` if no blocking issues
   remain.

2. **Per-action handlers** in
   `multitenancy/imports_v2/resolve_handlers.py` (new file):

   - `pick_row` — for `erp_id_conflict`. Drops all rows in the group
     except the one the operator picked. Re-runs conflict detection
     to remove the issue.
   - `skip_group` — drops every row of the conflicting group from
     the parsed payload.
   - `abort` — moves session to `error`.
   - `map_to_existing` — for `unmatched_reference` (see below).
     Params: `{target_id, create_substitution_rule: bool, rule: {match_type, match_value?, filter_conditions?}}`.
     Stages a rule on `session.staged_substitution_rules` and
     rewrites the parsed payload to use the mapped value.
   - `edit_value` — for `bad_date_format` and `negative_amount`.
     Params: `{row_id, field, new_value}`. Mutates the specific row
     in parsed_payload.
   - `ignore_row` — drops the specific row from parsed_payload.

3. **Additional issue detectors** (run in analyze for both modes):

   | Type                    | Detector                                                                     |
   |-------------------------|------------------------------------------------------------------------------|
   | `unmatched_reference`   | FK lookup failure — account/entity/cost center/currency string doesn't match any existing row. |
   | `je_balance_mismatch`   | Per erp_id group, Σdebit ≠ Σcredit on the JournalEntry sheet (template) OR on the combined Tx+autoJE rows (ETL). |
   | `bad_date_format`       | `date` column contains a value that doesn't parse via `_parse_date_value`.   |
   | `negative_amount`       | `amount` column is negative where the operator flagged a "positive-only" contract (new per-column hint). |
   | `fk_ambiguous`          | FK lookup returned > 1 match for the same key value.                         |

4. **Commit materialises staged rules** — in `commit_session()`
   before delegating to the write backend, loop through
   `session.staged_substitution_rules`, `SubstitutionRule.objects.create(...)`
   each one with `source=SOURCE_IMPORT_SESSION, source_session=session`,
   capture the created pks, and return them in the commit response as
   `substitution_rules_created`. Wrap everything in one
   `transaction.atomic()`.

5. **Editable summary pre-commit** — the `staged_substitution_rules`
   list is mutable between resolve calls. Frontend can PATCH each
   entry (new action `update_staged_rule`? or inline on the resolve
   payload as `{issue_id, action: "update_staged_rule", params: {index, rule: {...}}}`).
   Confirm behaviour when implementing.

**Tests**:

- Each issue type × each applicable action combo (matrix tests).
- Pick-row removes exactly one issue; remaining issues untouched.
- Map-to-existing creates a staged rule; commit materialises it
  with `source=import_session` + `source_session=FK`.
- Staged rule edit before commit lands correctly.
- Abort moves session to `error`; subsequent commit fails 409.
- End-to-end: analyze-with-conflicts → resolve each → commit → rows
  written AND rule created.

**Scope estimate**: ~600–800 LoC + ~400 LoC tests. One commit, or two
if the matrix of issue-detectors is large enough to split
(detection in its own commit, resolve handlers in another).

---

### Phase 5 — Frontend Path A (template v2) ✅ SHIPPED (commit `8d44dd4`)

Original design notes below preserved for reference. Shipped
deliverables: the toggle, `DiagnosticsPanel`, all six issue cards,
`SubstitutionAppliedBadge`, typed API client. Manual §11.10d also
landed alongside.

**Why now** — backend is feature-complete for operator-driven resolve
(Phase 4B). Nothing calls the v2 endpoints yet in the UI, so the
feature is invisible to users. Phase 5 gates any real-world exercise
of the detectors + handlers we just shipped.

**What** — extend `frontend/src/pages/imports/ImportTemplatesPage.tsx`
with a "Modo interativo (v2)" toggle next to the existing form (per
decision A.3). When ON, the form talks to the v2 endpoints and
shows a diagnostics panel below the preview.

**Action/issue matrix that the frontend needs to render** (derived
from the backend that now exists — do not invent new actions, the
resolve endpoint will 400 on anything not in this table):

| Issue type               | Proposed actions                                  | Card to build |
|--------------------------|---------------------------------------------------|---------------|
| `erp_id_conflict`        | `pick_row`, `skip_group`, `abort`                | IssueCardErpIdConflict |
| `missing_etl_parameter`  | `abort`                                           | IssueCardMissingParam (new) |
| `unmatched_reference`    | `map_to_existing`, `ignore_row`, `abort`         | IssueCardUnmatchedReference |
| `fk_ambiguous`           | `map_to_existing`, `ignore_row`, `abort`         | IssueCardFKAmbiguous (reuse above with candidate_ids pre-filled) |
| `bad_date_format`        | `edit_value`, `ignore_row`, `abort`              | IssueCardEditValue |
| `negative_amount`        | `edit_value`, `ignore_row`, `abort`              | IssueCardEditValue (reuse) |

**Deliverables**:

1. `frontend/src/features/imports/api.ts` — new `importsV2` object with
   `analyzeTemplate`, `commitSession`, `discardSession`, `resolve`,
   `getSession` methods.

2. `frontend/src/features/imports/types.ts` — `ImportSession`,
   `ImportIssue`, `SubstitutionApplied`, action payload shapes.

3. `frontend/src/components/imports/` (new subfolder):

   - `DiagnosticsPanel.tsx` — renders `open_issues` grouped by type.
   - `IssueCardErpIdConflict.tsx` — renders one `erp_id_conflict`
     with a "pick row / skip group / abort" form.
   - `IssueCardUnmatchedReference.tsx` — map-to-existing form with
     `SearchableAccountSelect` (reuse from reconciliation); includes
     the "criar regra de substituição" checkbox + match-type dropdown
     (exact / regex / caseless — the three types `SubstitutionRule`
     actually supports).
   - `SubstitutionAppliedBadge.tsx` — one `badge: old → new` badge;
     used in the "Substituições aplicadas" panel.

4. `ImportTemplatesPage.tsx` changes:

   - Add a toggle state `mode: "v1" | "v2"`.
   - When `v2`: on file upload → POST /v2/analyze/ → render
     `DiagnosticsPanel`. On "commit" click → POST /v2/commit/<id>/.
     On per-issue resolution → POST /v2/resolve/<id>/ and refresh.
   - When `v1`: unchanged — legacy behaviour stays as-is.

5. Manual **§11.10d** — write a new section walking operators through
   the v2 template flow end-to-end with screenshots. Match the voice
   of §11.10b (pt-BR, step-by-step, "Resultado esperado" JSON blocks).

**Tests** (Vitest + React Testing Library — check if present; if not,
cypress/playwright would replace unit with e2e but is slower):

- Toggle flips correctly.
- Analyze response with issues renders the diagnostics panel.
- Submitting a resolution calls the API with the right shape.
- Commit button disabled while `is_committable=false`.

**Scope estimate**: ~1000 LoC (components are the bulk) + ~300 LoC
tests + ~100 lines of manual. One commit.

---

### Phase 6 — Frontend Path B (ETL v2) ✅ SHIPPED (commit `f253e0f`)

Shipped with `transaction_groups` serializer field, ErpIdGroupsSection,
and the ETL-side reuse of Phase 5 components. Follow-ups 6.x / 6.y /
6.z-a through 6.z-h added rule dropdown, dry-run preview, async
analyze+commit, queue panel, session detail, cache reuse, live
progress, LookupCache perf, stale-session reaper, intra-atomic row
progress, and Celery Beat. See §1 status table for each commit ref.

Original design notes preserved below for reference.

**What** — mirror Phase 5 on `frontend/src/pages/imports/EtlImportPage.tsx`.
Same toggle pattern, same DiagnosticsPanel component reused.

**Deliverables** — the same component set as Phase 5, plus these
ETL-specific sections layered into the existing preview screen:

1. **"Grupos de `erp_id`"** — visualisation of how rows grouped into
   one Transaction each (per the Option-B / 2a semantics shipped in
   Phases 1–3). Each group shows: `erp_id`, row count, status
   (OK / conflict / imbalance), and an expand arrow to inspect the
   underlying rows.

2. **"Substituições aplicadas"** — list of `badge: old → new` chips
   populated from `session.substitutions_applied`. Reuses the
   `SubstitutionAppliedBadge` from Phase 5.

3. **"Parâmetros ausentes"** — renderer for `missing_etl_parameter`
   issues. Shows: expected column, operator role, list of columns
   that ARE present, and a direct-link "Editar regra de
   transformação" button that deep-links to the rule editor.

4. **"Referências não mapeadas"** — renderer for `unmatched_reference`
   issues (Phase 4 detects them). Uses `IssueCardUnmatchedReference`
   from Phase 5 identically.

5. Manual **§11.10e** — ETL v2 walkthrough. Like §11.10d but focused
   on transformation-rule setup + auto-JE config + interactive
   resolve.

**Scope estimate**: ~600 LoC (mostly layout — heavy reuse from
Phase 5) + ~200 LoC tests + manual section. One commit.

---

### Phase 7 — Remove legacy split-delete code ← next code task (when burn-in clears)

**Status**: gated on burn-in. v2 has been in prod since the 6.z-h
deploy (2026-04-24 window); do not start Phase 7 until the operator
team confirms they've run at least one month of real imports through
v2 without falling back to the legacy endpoints. Until then, keep the
legacy code paths as a safety net.

Once Phases 4–6 are in production and stable, delete the old split
handling in `multitenancy/tasks.py` and `multitenancy/etl_service.py`:

- `_delete_transactions_for_erp_ids_replace_import` (tasks.py:1244)
- `_collect_transaction_erp_id_counts_for_sheet` (tasks.py:1209) —
  NOW USED by the v2 grouping, so keep but rename or re-document;
  OR leave in place if v2 uses the Phase-0 grouping helper instead
  (it does — `_group_transaction_rows_by_erp_id` in `tasks.py`).
  Double-check before deleting.
- `erp_ids_with_splits_in_file` special case in
  `etl_service.py:2399-2408` and the mid-loop override at 2477-2480.
- Any related tests that were testing the split-delete behaviour.

**Precondition**: v2 endpoints must be the only active import path for
the split-erp_id case in production for at least one full
reconciliation cycle (e.g. one month of imports) before ripping out
the legacy code. Don't merge Phase 7 until that burn-in is
confirmed.

**Scope estimate**: ~200 LoC removed + ~50 LoC of test updates. One
commit.

---

## 3. Architectural decisions already locked

Don't re-litigate these; they're in the commits above. Listing for
the next-PC reader.

**Fork 1 — two legacy endpoints preserved**:
- `/api/core/bulk-import/` (template, one-shot)
- `/api/core/etl/{analyze,preview,execute}/` (ETL pipeline)

Both stay byte-identical. v2 mounts alongside at:
- `/api/core/imports/v2/{analyze,commit/<id>,sessions/<id>,resolve/<id>}/`
- `/api/core/etl/v2/{analyze,commit/<id>,sessions/<id>,resolve/<id>}/`

**Fork 2 — stateful multi-turn** via `ImportSession` model. Analyze
creates session; resolve mutates it; commit finalises. File bytes
persisted on the session for up to 24h (TTL via `expires_at` + a
cleanup Celery beat — not yet implemented; add in Phase 4 or a
small standalone commit).

**Fork 3 — match types**: `exact | regex | caseless` — the three that
`SubstitutionRule.match_type` already enforces. `startswith` and
`contains` are expressible via `regex` for now; explicit enum values
can be added later without a behavioural migration.

**Fork 4 — issue menu**:

| Issue type               | Phase | Notes                                                  |
|--------------------------|-------|--------------------------------------------------------|
| `erp_id_conflict`        | 2/3 ✅ | Detects; commit blocked                               |
| `missing_etl_parameter`  | 3 ✅  | ETL-only; detects; commit blocked                     |
| `unmatched_reference`    | 4     | Resolve with map_to_existing + auto-rule              |
| `je_balance_mismatch`    | 4     | Detect only; no inline fix (operator re-uploads)      |
| `bad_date_format`        | 4     | Resolve with edit_value                               |
| `negative_amount`        | 4     | Resolve with edit_value or ignore_row                 |
| `fk_ambiguous`           | 4     | Resolve with map_to_existing                          |

**Shared decisions**:
- S.1 stateful session ✓
- S.2 default match_type `exact`; UI dropdown exposes the 3 real options
- S.3 expanded issue menu (above)
- S.4 editable summary of auto-rule before commit
- S.5 everything tenant-scoped via `TenantAwareBaseModel`

**A.1** template import currently at `/imports/templates` route
(`ImportTemplatesPage.tsx`). Frontend UX is upload + dry-run preview
+ execute — mirror that with a v2 toggle.

**A.2** erp_id grouping applies ONLY to the `Transaction` model. Not
BankTransaction, not any other model.

**A.3** same URL, add a visible "Modo interativo (v2)" toggle.

**B.1** diagnostics panel renders inline in the existing preview
screen (not a new step). Four new sections: "Grupos de `erp_id`",
"Substituições aplicadas", "Parâmetros ausentes", "Referências não
mapeadas".

**B.2** erp_id grouping is mandatory in ETL v2 — no knob.

**B.3** existing transformation rules accepted as-is under v2.

---

## 4. Key file pointers

Backend:
- `multitenancy/imports_v2/__init__.py` — package marker
- `multitenancy/imports_v2/issues.py` — issue types + actions + helpers
- `multitenancy/imports_v2/services.py` — `analyze_template`,
  `analyze_etl`, `commit_session` (mode-aware), `discard_session`
- `multitenancy/imports_v2/views.py` — 4 APIViews
- `multitenancy/imports_v2/serializers.py` — `ImportSessionSerializer`
- `multitenancy/imports_v2/template_urls.py` — `/imports/v2/*`
- `multitenancy/imports_v2/etl_urls.py` — `/etl/v2/*`
- `multitenancy/models.py` (lines 441-505 and 786-end) —
  `SubstitutionRule.source`, `SubstitutionRule.source_session`,
  `ImportSession`
- `multitenancy/migrations/0035_v2_import_session.py` — the migration
- `multitenancy/tasks.py` — `_group_transaction_rows_by_erp_id`
  (grouping helper, reused by both modes)
- `multitenancy/etl_service.py` — legacy ETL pipeline (unchanged)

Tests:
- `multitenancy/tests/test_transaction_erp_id_grouping.py` — 13 tests
- `multitenancy/tests/test_import_session_model.py` — 9 tests
- `multitenancy/tests/test_imports_v2_backend.py` — 14 tests
- `multitenancy/tests/test_imports_v2_etl.py` — 9 tests

Manual:
- `docs/manual/11-etl-importacao.md` §11.10c — operator-facing semantics
  for erp_id grouping. §11.10d and §11.10e come in Phase 5/6.

Frontend insertion points (for Phase 5/6):
- `frontend/src/pages/imports/ImportTemplatesPage.tsx`
- `frontend/src/pages/imports/EtlImportPage.tsx`
- `frontend/src/features/imports/api.ts`
- `frontend/src/features/imports/types.ts`

---

## 5. Development tips

**Running tests locally**:
- First run: `--create-db` (~9 min on Windows).
- Subsequent runs: `--reuse-db` (~2–3 min).
- If a model change invalidates the reused DB, delete the SQLite
  file under the worktree root or switch back to `--create-db`.

**Running the dev server**:
- Launch config is at `.claude/launch.json` — name `nord-frontend`
  runs Vite on port 3101.
- Backend should run separately (Django `runserver` or whatever
  the ops playbook uses).

**Mocking the ETL pipeline in tests**:
- Patch `multitenancy.imports_v2.services.ETLPipelineService`. The
  symbol is imported at module level (Phase 3 fixed the previous
  deferred-import issue). See
  `multitenancy/tests/test_imports_v2_etl.py` for the pattern.

**Debugging a session**:
- `GET /api/core/imports/v2/sessions/<id>/` returns the serialised
  session including all JSON blobs (`open_issues`, `resolutions`,
  `staged_substitution_rules`, `parsed_payload`, `result`) — enough
  to reproduce locally.

**Common pitfalls hit during Phase 2–3**:
- `CustomUser` has no `company_id` field (user↔company is via
  `UserCompanyMembership`). Tests use URL-based tenant resolution.
- `ImportTransformationRule` has no `auto_create_journal_entries`
  field — config lives in the request body (matches legacy). Tests
  pass it as a JSON string multipart field.
- `pandas.read_excel` auto-parses date-looking strings into
  `Timestamp`; services.py has a `_json_scalar` normaliser that
  converts to ISO strings before JSONField storage.
- `TenantMiddleware` bypasses paths starting with `/api/core/...` —
  so `request.tenant` is only set when the URL starts with
  `/<tenant_id>/...`. v2 URLs follow that pattern; legacy flat
  `/api/core/...` URLs would not.

---

## 6. Open questions (for future sessions)

None blocking. Two things worth revisiting if Phase 4 or 5 uncover
new constraints:

1. **Staged-rule editing semantics** — how does the frontend PATCH a
   staged rule? Either a new resolve action (`update_staged_rule`)
   or a dedicated endpoint. Pick when writing Phase 4.

2. **Celery cleanup beat for expired sessions** — `expires_at` is
   set on every session but no task sweeps them yet. Add a small
   `cleanup_expired_import_sessions` task to `multitenancy/tasks.py`
   and register it in Celery beat in Phase 4 or as a standalone
   commit. Risk is low (sessions that aren't swept just accumulate
   file_bytes in the DB — we already clear that on commit/discard
   so only truly abandoned sessions hold bytes).

---

*Last updated: 2026-04-24, after the 6.z-h ops follow-ups
(head of main `296735f`). All coded phases 1–6.z-h are in prod.
Next session: start with §1 status, then either wait on Phase 7
burn-in or pick up the B1–B4 backend backlog.*

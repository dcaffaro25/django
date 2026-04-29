# CLAUDE.md — Session Handoff

Concise notes for the next Claude session. Optimised for signal-
to-noise: skim the headings, dive into a section only when you
hit something it covers.

---

## 1. Repo at a glance

- **Backend**: Django + DRF, Postgres + pgvector, Celery, MPTT
  trees on Account. Settings module: `nord_backend.settings`. Main
  app: `accounting/`. Multi-tenant via `multitenancy/` (subdomain
  resolves to `request.tenant`; `'all'` is the cross-tenant
  superuser scope).
- **Frontend**: React + TypeScript + Vite + Tailwind. Lives in
  `frontend/`. React Query for server state. UI primitives in
  `frontend/src/components/ui` (shadcn-style). Reports page is
  `frontend/src/pages/reports/StandardReportsPage.tsx`.
- **Shell**: User runs PowerShell on Windows. **No `&&`** —
  chain commands with `;` or use parameter `working_directory`.
  No `tail`, `cat`, `grep`. Use the dedicated tools instead.
- **Build**: Frontend builds in Docker (`npm run build`); local
  shell does NOT have `node`/`npm` in PATH. Don't try to invoke
  `tsc` directly — rely on lints + careful reading.
- **Git**: Default branch is `main`. Multi-line commit messages
  via `git commit -F .git/COMMIT_EDITMSG_DRAFT` (heredoc doesn't
  work in PowerShell). NEVER force-push, NEVER amend without
  verifying authorship + push state.

---

## 2. Recent work (most recent first)

### `5bfea5e` — perf(reports): close cache invalidation gaps

- Added composite indexes `(company, updated_at)` on
  `Account`, `Transaction`, `JournalEntry` (migration
  `accounting/migrations/0080_report_cache_updated_at_indexes.py`).
  Speeds up `report_cache.data_version()` from filtered seq-scan
  to single index seek per probe.
- Added 5 explicit `bump_version(company_id)` calls at every
  audited bulk-write site:
  - `accounting/views.py` undo-reconciliation handler (around
    line ~1100): `BankTransaction.balance_validated` /
    `JournalEntry.is_reconciled` flips.
  - `accounting/views.py` ×2 reconciliation finalize handlers
    (v1 ~line 4524 and v2 ~line 4990): `JournalEntry.bulk_update`
    of `[account, bank_designation_pending]`.
  - `accounting/admin.py` ×2 balance-recompute helpers
    (`recompute_balances_for_accounts` ~line 552 and
    `batch_update_parent_balances` ~line 618):
    `Account.bulk_update(['balance'])`.
- All five paths use `try/except` around the bump — cache
  hiccup must never break the underlying business op.

### `8ed1b6a` — perf(reports): versioned cache + DB-side anchor

- New `accounting/services/report_cache.py` (the cache layer —
  see § 3 for architecture).
- `compute_financial_statements_cached()` wrapper added in
  `accounting/services/financial_statements.py`. Endpoint
  `GET /api/accounts/financial-statements/` now goes through it.
  `?nocache=1` short-circuits.
- `AccountViewSet.get_serializer_context` (`accounting/views.py`):
  - The expensive `delta_map` build is now wrapped in
    `cached_payload`, so paginated CoA reads (page 2, 3, …) for
    the same `(tenant, basis, date_from, date_to, entity,
    include_pending)` tuple reuse the first page's build.
  - The posted-bucket aggregation was rewritten: replaced
    `(account_id, transaction.date)` GROUP BY + Python anchor
    filter with a correlated `Subquery` on `Account.balance_date`
    that pushes `transaction.date > balance_date` into the WHERE
    clause. Single `GROUP BY account_id`, far fewer rows
    materialised.
  - `include_pending` parsing was de-duplicated up to the top
    of the method (was parsed twice before).

### `c267a51` — feat(reports): exportable demonstrativos + UI polish

- `AccountWiringModal` body is scrollable
  (`flex max-h-[90vh]` column + inner `overflow-y-auto`); 36-tag
  grid no longer clips the Save/Cancel row on short screens.
- DRE tab capped at `max-w-3xl` and centred (`StandardReportsPage`,
  `DreTab`).
- Excel + PDF export buttons in the actions bar
  (`ReportExportButtons`):
  - PDF: client-side `html2pdf.js` (lazy import); each tab's
    container is tagged with `[data-statement-card]`.
  - Excel: server-side. New endpoint flag `?format=xlsx` returns
    a 4-sheet workbook (DRE / Balanço / DFC / Memória de
    Cálculo) with formula-driven subtotals. Implemented in
    `accounting/services/financial_statements_xlsx.py` (uses
    `openpyxl`).

### Earlier this work-train (referenced by transcript)

- `6a709f5` perf(reports): pre-aggregated `/financial-statements/`
  endpoint (replaced 3MB CoA payload + client-side aggregation).
- `7704057` perf(coa): kill `FlexibleRelatedField` N+1.
- `9bff886` feat(accounting): `cashflow_category` field +
  Evolat backfill.

---

## 3. Report cache architecture (the non-obvious part)

`accounting/services/report_cache.py` — read this file first if
you're touching report perf. Public surface:

```python
data_version(company_id) -> str             # fingerprint
bump_version(company_id) -> None            # force-invalidate
cached_payload(prefix, company_id, key_parts, builder, ...) -> Any
```

### Fingerprint composition

The cache key includes a fingerprint that moves on **either** of
two sources:

1. `MAX(updated_at)` across `JournalEntry`, `Transaction`,
   `Account` for the tenant. Covers every `.save()` write
   (because `BaseModel.updated_at` has `auto_now=True`).
2. A per-tenant epoch counter, manually bumped by callers via
   `bump_version()`. Covers `QuerySet.update()` /
   `bulk_update()` / raw SQL — paths that bypass `auto_now`.

Final TTL of 60s is a defence-in-depth floor for anything that
slips through both, NOT the primary freshness mechanism.

### Freshness contract

| Write path | Invalidation |
|---|---|
| `obj.save()` | Automatic via `auto_now=True` |
| `QuerySet.update()` / `bulk_update()` at audited sites | Explicit `bump_version()` already wired |
| New code doing `.update()` / `bulk_update()` on JE/Tx/Account | **You must add `bump_version(tenant.id)` after the write.** Audit pattern: grep the diff for `\.update\(` / `bulk_update\(` on those three models. |
| Raw SQL / COPY / DataFrame.to_sql | Same as above |

### Cache backend

No `CACHES` setting → Django default `LocMemCache` (per-process).
Single-worker deployments are fine; multi-worker setups should
add Redis to share the epoch counter across workers. No code
changes needed for the swap.

### Debug switch

Append `?nocache=1` to:
- `GET /api/accounts/` (CoA list — bypasses delta_map cache)
- `GET /api/accounts/financial-statements/` (Demonstrativos)

…to force a rebuild. Useful when a tenant reports stale numbers
(verify it's a cache issue vs a real bug) or for benchmarking
the cold-cache path.

---

## 4. Reports page architecture

Frontend lives in `frontend/src/pages/reports/`:

- `StandardReportsPage.tsx` — TabbedShell with `DreTab`,
  `BalancoTab`, `DfcTab`, plus Personalizados (custom report
  builder).
- `components/AccountWiringModal.tsx` — pencil-icon entry point
  for editing `report_category` / `cashflow_category` / `tags`
  in-place from any account row.
- `components/DrillableLine.tsx` — collapsible statement line
  with per-account drill-down via `useAccount(id)`.
- `components/JournalEntriesPanel.tsx` — JE drill panel.
- Filters live in URL params (`include_pending`, `date_from`,
  `date_to`, `entity`, `basis`); read via `useReportFilters()`
  inside `StandardReportsPage.tsx`. Bookmarkable / shareable.

Backend pipeline:

```
GET /api/accounts/financial-statements/
  -> AccountViewSet.financial_statements (views.py)
  -> compute_financial_statements_cached (services/financial_statements.py)
    -> [cache miss] compute_financial_statements
      -> _walk_taxonomy           (resolve effective_category)
      -> _accrual_per_account_deltas  OR  compute_cash_basis_book_deltas
      -> compute_cashflow_direct  (from cashflow_service.py)
      -> categories[] + cashflow{} + cash_total
```

Sign convention: per-account JE deltas are sign-corrected by
`account_direction` (positive = balance increased). Anchor
`Account.balance` is included only for Balanço-side categories;
`FLOW_CATEGORIES` (DRE) drop the anchor.

Basis toggle: `?basis=accrual` (default; `transaction.date`-
scoped) vs `?basis=cash` (uses bank-leg cash dates with
proportional weighting per `cashflow_service`).

---

## 5. Common operations

### Run lints (preferred over building)

Use the `ReadLints` tool on the files you edited. The frontend
build daemon is in Docker — local shell can't `npm run build`.

### Make a multi-line commit (PowerShell)

```powershell
# Write the message to a draft file first (heredoc doesn't work in PS)
# Then:
git commit -F .git/COMMIT_EDITMSG_DRAFT
# Clean up afterwards:
Remove-Item .git/COMMIT_EDITMSG_DRAFT
```

### What to skip when staging

The repo carries some intentionally-untracked Claude artefacts
that should NOT be committed:

- `.claude/launch.json` (modified locally; stays in working tree)
- `.claude/scheduled_tasks.lock`, `.claude/settings.local.json`
- `.claude/worktrees/`
- `frontend/retool/Nord%20App%20-%20Production/lib/` (Retool
  exports the operator hand-saves; ignored by intent)

Pattern: stage explicitly by path, never `git add -A`.

### Migrate after schema changes

```bash
python manage.py migrate accounting
```

Migration `0080` adds three indexes via plain `AddIndex`
(`CREATE INDEX`, blocking). On Evolat-scale tables it's sub-
second; for multi-million-row tables, switch the operations to
`AddIndexConcurrently` in a follow-up before deploying.

---

## 6. Open follow-ups (low priority, not blocking)

These were considered and deferred — pick up if relevant work
brings you near them:

- **MPTT `tree_id` filter in cashflow weighting**
  (`accounting/services/cashflow_service.py`,
  `_compute_transaction_weights`): if it iterates accounts in
  Python instead of pre-filtering SQL-side
  (`Account.objects.filter(tags__contains=['cash'])`), there's a
  10-100× win on the weighting step for large CoAs.
- **`_walk_taxonomy` → SQL recursive CTE**: Python loop over
  account rows for `effective_category` resolution. <1ms on
  Evolat (356 rows); revisit if any tenant exceeds ~5k accounts.
- **Prefetch reports payload on tab hover** in
  `StandardReportsPage.tsx`: `queryClient.prefetchQuery` when the
  user hovers DRE/Balanço/DFC tabs so the click-to-render is
  instant.
- **`AddIndexConcurrently` migration variant**: if a tenant's
  `JournalEntry` table grows past a few million rows, swap the
  default `AddIndex` operations in `0080` for the concurrent
  variants to avoid blocking writes during deploy.
- **Redis CACHES backend**: no code change needed, just settings.
  Worth doing once multi-worker matters or memory pressure on
  LocMemCache becomes visible.

---

## 7. Pitfalls / gotchas (don't re-learn these)

- **PowerShell**: `&&` is not a statement separator. Use `;`. No
  heredoc — write commit messages to a file first. `tail`, `cat`,
  `grep` don't exist; use the dedicated tools.
- **DRF perform_create/update**: `auto_now` fires automatically;
  do NOT add a redundant `bump_version()` there.
- **`bulk_update()` and `QuerySet.update()`**: bypass `auto_now`.
  Always pair with `bump_version(tenant.id)` if the fields
  touched can affect reports (`account`, `state`, `date`,
  `balance`, `balance_date`, `account_direction`,
  `report_category`, `cashflow_category`, `tags`, `parent_id`,
  `is_reconciled`, `transaction.balance_validated`,
  `debit_amount`, `credit_amount`).
- **Don't commit `.claude/launch.json` modifications**. The
  user's local launch config drifts; it's not meant to be
  versioned even though it's tracked.
- **Frontend imports from `@/features/reconciliation`** — the
  barrel re-exports from `./hooks`, `./api`, `./types`, etc. If
  you add a hook, it's automatically exposed.
- **Number formatting**: Brazilian accounting uses
  `#,##0.00;(#,##0.00);"-"`. Both the XLSX exporter and the
  frontend `formatCurrency` agree on this; if you add a new
  display, mirror it.
- **`formatCurrency(value, currency)` in the frontend**: the
  `currency` arg is required for `format="currency"` but
  optional for `format="int"`. The `KpiCard` interface reflects
  this; keep it consistent if you copy.

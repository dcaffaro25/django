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

### Uncommitted — Billing module: NF↔Tx links, fiscal status, auto-create Invoice

Multi-phase feature linking the existing siloed Invoice / NotaFiscal /
Contract surfaces to each other and (eventually) to the GL. Phases 1, 2,
2.5, 3 landed; phase 4 (actual GL posting) deliberately deferred.

- New models in `billing/`:
  - `NFTransactionLink` ([billing/models_nf_link.py](billing/models_nf_link.py))
    — M:N between `accounting.Transaction` and `billing.NotaFiscal`.
    Carries `confidence`, `method`, `matched_fields`, `review_status`
    (suggested/accepted/rejected), and snapshot columns for stale-link
    detection. **Read-only against accounting** — no FKs added on
    `Transaction` / `JournalEntry`.
  - `InvoiceNFLink` ([billing/models.py](billing/models.py)) —
    through-model for the new `Invoice ↔ NotaFiscal` M2M, with
    `relation_type` (normal / devolucao / complementar / ajuste) and
    optional `allocated_amount` for partial coverage.
  - `BillingTenantConfig` ([billing/models_config.py](billing/models_config.py))
    — singleton-per-tenant feature flags + posting defaults
    (default A/R, default A/P).
  - `Invoice.contract` FK, `Invoice.fiscal_status` (six-state enum:
    `pending_nf`/`invoiced`/`partially_returned`/`fully_returned`/
    `fiscally_cancelled`/`mixed`), `Invoice.has_pending_corrections`
    (CCe flag), and `Invoice.notas_fiscais` M2M (through `InvoiceNFLink`).
  - `BusinessPartner.{receivable,payable}_account` FKs.
  - Bug fix: `ProductService.code` is now `(company, code)` unique
    (was global unique — different tenants couldn't share codes).
- Migration: [billing/migrations/0020_nf_link_invoice_relations_partner_accounts.py](billing/migrations/0020_nf_link_invoice_relations_partner_accounts.py)
  — purely additive (Add/Create), no data migration. Applied cleanly.
- Services (all isolated, callable from anywhere):
  - [billing/services/nf_link_service.py](billing/services/nf_link_service.py)
    — `find_candidates`, `persist_links`, `accept_link`, `reject_link`,
    `rescan_for_nf`, `rescan_for_transaction`. Matching passes:
    1. `Transaction.nf_number == NotaFiscal.numero` (+0.50)
    2. CNPJ ∈ {emit, dest} (+0.25)
    3. Date within window (+0.15)
    4. Amount within tolerance (+0.10)
    Plus regex fallback over `Transaction.description` (+0.30 base).
    Confidence clamped to [0, 1]. Calls `bump_version` only when an
    accepted row is created.
  - [billing/services/fiscal_status_service.py](billing/services/fiscal_status_service.py)
    — `compute_fiscal_status(invoice)`, `refresh(invoice)`,
    `refresh_for_nf(nf)`. Reads NF chain (eventos for cancelamento +
    CCe, NotaFiscalReferencia for devolução). Cancelamento detected by
    NFeEvento `tipo_evento ∈ {110111, 110112}` with SEFAZ
    `status_sefaz` 135 or 155.
  - [billing/services/nf_invoice_sync.py](billing/services/nf_invoice_sync.py)
    — `match_or_create_invoice_for_nf` (gated on tenant flag +
    finalidade/tipo whitelist), `attach_invoice_to_nf` (idempotent
    M:N attach + fiscal_status refresh).
- Hook points (explicit calls, not signals — keeps the chain auditable):
  - [billing/services/nfe_import_service.py:545](billing/services/nfe_import_service.py:545)
    `_post_import_billing_hooks` runs link rescan + invoice
    match-or-create + fiscal_status refresh inside the import txn,
    each in try/except.
  - [billing/services/nfe_event_import_service.py:106](billing/services/nfe_event_import_service.py:106)
    cancelamento / CCe events trigger `refresh_for_nf` for any
    Invoices linked via the M2M.
- API surface ([billing/views.py](billing/views.py),
  [billing/urls.py](billing/urls.py)):
  - `nf-transaction-links/` ViewSet + `/scan/`, `/accept-all-above/`,
    per-row `/accept/`, `/reject/` actions.
  - `invoice-nf-links/` ViewSet (delete refreshes fiscal_status).
  - `billing-config/` ViewSet with `/current/` GET/PATCH for the
    singleton row.
  - `invoices/<id>/attach-nf/` and `invoices/<id>/refresh-fiscal-status/`
    custom actions.
  - Invoice list filters: `fiscal_status`, `status`, `partner`,
    `date_from/to`.
- Mgmt command:
  `python manage.py rescan_nf_links --tenant evolat --dry-run`
  (also `--all-tenants`, `--auto-accept-above`, `--limit`,
  `--min-confidence`, `--date-window-days`, `--amount-tolerance`).
  Backfill on Evolat surfaced 515 candidate matches at 100% confidence
  on real data.
- Frontend (new module under `frontend/src/features/billing/` + pages
  in `frontend/src/pages/billing/`):
  - `BillingHubPage` — TabbedShell at `/billing` with 4 routable tabs:
    Faturas / Notas Fiscais / Vínculos NF↔Tx / Configurações.
    The Vínculos tab badge shows pending suggestion count.
  - `InvoicesPage` + `InvoiceDetailDrawer` — list + drawer with NF
    attachments, attach-NF modal (NF picker + relation_type + allocated
    amount), refresh-fiscal-status button. Two-axis filter: payment
    status × fiscal_status.
  - `NotasFiscaisPage` — read-only list of imported NFs with
    finalidade/tipo filters and SEFAZ status pill.
  - `NfLinkReviewPage` — confidence-banded sub-tabs (Sugeridos /
    Aceitos / Rejeitados), side-by-side Tx ↔ NF cards, accept/reject
    with optimistic update, Rodar scan modal (date_window, tolerance,
    min_confidence, dry_run), Aceitar em massa modal (single
    confidence threshold).
  - `BillingSettingsPage` — three sections: link tuning, auto-create
    gates, posting account defaults. Closes with an info banner stating
    GL posting (Phase 4) isn't active yet.

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
  `debit_amount`, `credit_amount`). Also when bulk-flipping
  `NFTransactionLink.review_status` to `accepted` (see
  `accept_all_above` action in [billing/views.py](billing/views.py)
  — already wired). Per-row save() paths in
  `nf_link_service.accept_link` / `reject_link` go through `.save()`
  but still bump explicitly because the link table is auditable from
  reports and we want immediate cache invalidation.
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

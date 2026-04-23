# Imports v2 — Implementation Plan

Handover document for the v2 interactive-import feature (analyze →
resolve → commit, with `SubstitutionRule` auto-creation). Legacy
bulk-import (`/api/core/bulk-import/`) and legacy ETL
(`/api/core/etl/preview|execute|analyze/`) stay untouched throughout.

Read this once when resuming on a new machine, then the numbered
Phase sections for the specific next step.

---

## 1. Status summary

Six commits on `main`, in order:

| Ref         | What shipped                                                                 |
|-------------|------------------------------------------------------------------------------|
| `adf732d`   | Pure grouping helper `_group_transaction_rows_by_erp_id` + 13 unit tests     |
| `ff9e664`   | Manual §11.10c — erp_id grouping semantics for Transaction imports (pt-BR)   |
| `6882a25`   | Phase 1 — `ImportSession` model + `SubstitutionRule.source` field + tests    |
| `8c56913`   | Phase 2 — Template v2 backend (analyze + commit) + 14 tests                  |
| `0cc9835`   | Phase 3 — ETL v2 backend (analyze + commit) + 9 tests                        |
| `<pending>` | Phase 3.6 — Engine perf (pre-compile) + `skip_substitutions` hint + 25 tests |

Nothing uncommitted. Feature branch is `claude/adoring-wing-665ba7`
and tracks `origin/main` exactly; delete the branch or continue on
it, either works.

### Tests pass live on these paths

Both modes work end-to-end for clean files (no issues → READY →
commit). Files with issues land in `awaiting_resolve` and commit
returns 409 — that's intentional until Phase 4 ships the resolve
endpoint.

### Run the full v2 test suite

```bash
DJANGO_SETTINGS_MODULE=nord_backend.settings \
  python -m pytest \
    multitenancy/tests/test_transaction_erp_id_grouping.py \
    multitenancy/tests/test_import_session_model.py \
    multitenancy/tests/test_imports_v2_backend.py \
    multitenancy/tests/test_imports_v2_etl.py \
    multitenancy/tests/test_substitution_engine_perf.py \
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

### Phase 4 — Resolve endpoint + `SubstitutionRule` auto-creation

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

### Phase 5 — Frontend Path A (template v2)

**What** — extend `frontend/src/pages/imports/ImportTemplatesPage.tsx`
with a "Modo interativo (v2)" toggle next to the existing form (per
decision A.3). When ON, the form talks to the v2 endpoints and
shows a diagnostics panel below the preview.

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

### Phase 6 — Frontend Path B (ETL v2)

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

### Phase 7 — Remove legacy split-delete code

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

*Last updated: alongside Phase 3 ship (commit `0cc9835`).*

"""Reconciliation Agent — autonomous companion to the manual flow.

Iterates over unreconciled :class:`accounting.models.BankTransaction` rows,
calls :class:`BankTransactionSuggestionService` and decides for each one of:

* **auto_accepted** — top suggestion is high confidence + dominant + safely
  link-only (an existing balanced JE), so we create the
  :class:`Reconciliation`, mark the JE reconciled, and move on.
* **ambiguous** — top suggestion is above ``min_confidence`` but either too
  close to second-best or requires creating new JEs. Logged for human review.
* **no_match** — nothing meets ``min_confidence``.
* **not_applicable** — top is high confidence but its shape isn't safe for
  full automation (unbalanced, or ``create_new`` style).
* **error** — service threw.

Every run leaves a :class:`ReconciliationAgentRun` row and per-bank-tx
:class:`ReconciliationAgentDecision` rows. No JE is ever created by the
agent — only links to existing JEs are created. This is the v1 safety
guarantee. Future iterations can lift it (with explicit thresholds) once
the no-regret cohort is large enough to trust.

Trigger paths:

* ``python manage.py run_reconciliation_agent --tenant evolat --dry-run`` —
  ad-hoc replay / preview.
* Celery task wrapping :meth:`ReconciliationAgent.run` (not yet wired).
* Direct call from the MCP server tool ``run_reconciliation_agent``
  (also not yet exposed — read-only first).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from accounting.models import (
    BankTransaction,
    JournalEntry,
    Reconciliation,
    ReconciliationAgentDecision,
    ReconciliationAgentRun,
)
from accounting.services.bank_transaction_suggestion_service import (
    BankTransactionSuggestionService,
)

log = logging.getLogger(__name__)

# Defaults — overridable via settings or per-call kwargs. Tuned conservatively;
# operations should adjust ``RECONCILIATION_AGENT_AUTO_ACCEPT_THRESHOLD`` only
# after observing the false-positive rate over a populated cohort.
DEFAULT_AUTO_ACCEPT_THRESHOLD = Decimal("0.95")
DEFAULT_AMBIGUITY_GAP = Decimal("0.10")
DEFAULT_MIN_CONFIDENCE = Decimal("0.50")

OUTCOME_AUTO_ACCEPTED = "auto_accepted"
OUTCOME_AMBIGUOUS = "ambiguous"
OUTCOME_NO_MATCH = "no_match"
OUTCOME_NOT_APPLICABLE = "not_applicable"
OUTCOME_ERROR = "error"


@dataclass
class AgentRunResult:
    """Returned by :meth:`ReconciliationAgent.run`."""

    run_id: int
    n_candidates: int = 0
    n_auto_accepted: int = 0
    n_ambiguous: int = 0
    n_no_match: int = 0
    n_not_applicable: int = 0
    n_errors: int = 0
    decisions: list[dict[str, Any]] = field(default_factory=list)


def _D(value) -> Decimal:
    """Decimal-safe coercion."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _conf_setting(name: str, default: Decimal) -> Decimal:
    """Read an agent threshold from Django settings, falling back to default."""
    raw = getattr(settings, name, None)
    if raw is None:
        return default
    return _D(raw)


def _is_safe_to_auto_accept(suggestion: dict[str, Any]) -> tuple[bool, str]:
    """Decide if *suggestion* is structurally safe for full automation.

    Returns ``(ok, reason)``. The reason is recorded on ``not_applicable``
    decisions so the operator knows why the agent stepped aside.
    """
    stype = suggestion.get("suggestion_type")
    if stype != "use_existing_book":
        return False, f"suggestion_type={stype!r} (only 'use_existing_book' is auto-accepted)"
    if not suggestion.get("is_balanced", False):
        return False, "suggestion is not balanced (would require creating complementing JEs)"
    if suggestion.get("complementing_journal_entries"):
        # Defensive — even if is_balanced is True, refuse to fan out new JEs in v1.
        return False, "suggestion would create new JEs (v1 only links existing JEs)"
    if not suggestion.get("existing_journal_entry"):
        return False, "no existing_journal_entry to link"
    return True, ""


class ReconciliationAgent:
    """Autonomous reconciliation pass over a tenant's unreconciled bank txs.

    Each decision is recorded in an audit table; the only mutating action it
    can take is to create a :class:`Reconciliation` linking one bank tx to
    one existing balanced :class:`JournalEntry`. Anything riskier is flagged
    for a human.
    """

    def __init__(
        self,
        company_id: int,
        *,
        auto_accept_threshold: Decimal | float | str | None = None,
        ambiguity_gap: Decimal | float | str | None = None,
        min_confidence: Decimal | float | str | None = None,
        dry_run: bool = False,
        triggered_by: str = "",
        triggered_by_user_id: int | None = None,
    ):
        self.company_id = company_id
        self.auto_accept_threshold = (
            _D(auto_accept_threshold)
            if auto_accept_threshold is not None
            else _conf_setting(
                "RECONCILIATION_AGENT_AUTO_ACCEPT_THRESHOLD",
                DEFAULT_AUTO_ACCEPT_THRESHOLD,
            )
        )
        self.ambiguity_gap = (
            _D(ambiguity_gap)
            if ambiguity_gap is not None
            else _conf_setting(
                "RECONCILIATION_AGENT_AMBIGUITY_GAP", DEFAULT_AMBIGUITY_GAP
            )
        )
        self.min_confidence = (
            _D(min_confidence)
            if min_confidence is not None
            else _conf_setting(
                "RECONCILIATION_AGENT_MIN_CONFIDENCE", DEFAULT_MIN_CONFIDENCE
            )
        )
        self.dry_run = bool(dry_run)
        self.triggered_by = triggered_by[:64]
        self.triggered_by_user_id = triggered_by_user_id

        self._suggestion_service = BankTransactionSuggestionService(
            company_id=company_id
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(
        self,
        *,
        bank_account_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int | None = None,
    ) -> AgentRunResult:
        """Execute one pass and return aggregate counters + decisions."""

        run = self._open_run(
            bank_account_id=bank_account_id,
            date_from=date_from,
            date_to=date_to,
            bank_tx_limit=limit,
        )
        result = AgentRunResult(run_id=run.id)

        try:
            candidates = self._candidate_bank_transactions(
                bank_account_id=bank_account_id,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
            )
            result.n_candidates = len(candidates)
            log.info(
                "reconciliation_agent.run start company=%s n=%d dry_run=%s",
                self.company_id, result.n_candidates, self.dry_run,
            )

            for bank_tx in candidates:
                decision_dict = self._process_one(run=run, bank_tx=bank_tx, result=result)
                result.decisions.append(decision_dict)

            self._close_run(run, result, status="completed")

            if not self.dry_run and result.n_auto_accepted > 0:
                self._bump_cache_version()

        except Exception as exc:
            log.exception("reconciliation_agent.run failed company=%s: %s", self.company_id, exc)
            self._close_run(run, result, status="failed", error_message=str(exc))
            raise

        return result

    # ------------------------------------------------------------------
    # Decision logic
    # ------------------------------------------------------------------
    def _process_one(
        self,
        *,
        run: ReconciliationAgentRun,
        bank_tx: BankTransaction,
        result: AgentRunResult,
    ) -> dict[str, Any]:
        """Decide & act on a single bank transaction."""

        try:
            wrapped = self._suggestion_service.suggest_book_transactions(
                bank_transaction_ids=[bank_tx.id],
                max_suggestions_per_bank=5,
                min_confidence=float(self.min_confidence),
            )
        except Exception as exc:
            log.exception("agent.suggest_failed bank_tx=%s: %s", bank_tx.id, exc)
            self._record_decision(
                run=run, bank_tx=bank_tx, outcome=OUTCOME_ERROR,
                top=None, second=None, suggestion_payload={},
                error_message=f"{type(exc).__name__}: {exc}",
            )
            result.n_errors += 1
            return {"bank_transaction_id": bank_tx.id, "outcome": OUTCOME_ERROR, "error": str(exc)}

        suggestions = self._unpack_suggestions(wrapped, bank_tx.id)

        if not suggestions:
            self._record_decision(
                run=run, bank_tx=bank_tx, outcome=OUTCOME_NO_MATCH,
                top=None, second=None, suggestion_payload={},
            )
            result.n_no_match += 1
            return {"bank_transaction_id": bank_tx.id, "outcome": OUTCOME_NO_MATCH}

        top = suggestions[0]
        second = suggestions[1] if len(suggestions) > 1 else None
        top_conf = _D(top.get("confidence_score") or 0)
        second_conf = _D(second.get("confidence_score") or 0) if second else None

        # Tier 1: below min_confidence → no_match
        if top_conf < self.min_confidence:
            self._record_decision(
                run=run, bank_tx=bank_tx, outcome=OUTCOME_NO_MATCH,
                top=top_conf, second=second_conf, suggestion_payload=top,
            )
            result.n_no_match += 1
            return {"bank_transaction_id": bank_tx.id, "outcome": OUTCOME_NO_MATCH}

        # Tier 2: above min but below auto-accept → ambiguous
        if top_conf < self.auto_accept_threshold:
            self._record_decision(
                run=run, bank_tx=bank_tx, outcome=OUTCOME_AMBIGUOUS,
                top=top_conf, second=second_conf, suggestion_payload=top,
            )
            result.n_ambiguous += 1
            return {
                "bank_transaction_id": bank_tx.id,
                "outcome": OUTCOME_AMBIGUOUS,
                "top_confidence": str(top_conf),
            }

        # Tier 3: above auto-accept BUT second too close → ambiguous
        if second_conf is not None and (top_conf - second_conf) < self.ambiguity_gap:
            self._record_decision(
                run=run, bank_tx=bank_tx, outcome=OUTCOME_AMBIGUOUS,
                top=top_conf, second=second_conf, suggestion_payload=top,
                error_message="top-second gap below ambiguity_gap",
            )
            result.n_ambiguous += 1
            return {
                "bank_transaction_id": bank_tx.id,
                "outcome": OUTCOME_AMBIGUOUS,
                "top_confidence": str(top_conf),
                "second_confidence": str(second_conf),
            }

        # Tier 4: structurally safe?
        ok, reason = _is_safe_to_auto_accept(top)
        if not ok:
            self._record_decision(
                run=run, bank_tx=bank_tx, outcome=OUTCOME_NOT_APPLICABLE,
                top=top_conf, second=second_conf, suggestion_payload=top,
                error_message=reason,
            )
            result.n_not_applicable += 1
            return {
                "bank_transaction_id": bank_tx.id,
                "outcome": OUTCOME_NOT_APPLICABLE,
                "reason": reason,
            }

        # Tier 5: green — auto accept (or dry-run preview)
        recon_id: int | None = None
        if not self.dry_run:
            recon_id = self._auto_accept(bank_tx=bank_tx, suggestion=top)

        self._record_decision(
            run=run, bank_tx=bank_tx, outcome=OUTCOME_AUTO_ACCEPTED,
            top=top_conf, second=second_conf, suggestion_payload=top,
            reconciliation_id=recon_id,
        )
        result.n_auto_accepted += 1
        return {
            "bank_transaction_id": bank_tx.id,
            "outcome": OUTCOME_AUTO_ACCEPTED,
            "top_confidence": str(top_conf),
            "reconciliation_id": recon_id,
        }

    # ------------------------------------------------------------------
    # Side effects
    # ------------------------------------------------------------------
    def _auto_accept(self, *, bank_tx: BankTransaction, suggestion: dict[str, Any]) -> int:
        """Create the :class:`Reconciliation` and mark sides as reconciled.

        Mirrors the manual finalize path in ``accounting/views.py`` (around
        line 4545): create the recon row, set the M2M sides, then explicitly
        flip ``BankTransaction.balance_validated`` and
        ``JournalEntry.is_reconciled``. ``QuerySet.update()`` is used for the
        flips because they bypass ``auto_now`` and we bump the report-cache
        version manually after the run.
        """
        je_data = suggestion.get("existing_journal_entry") or {}
        je_id = je_data.get("id")
        if not je_id:
            raise RuntimeError(
                f"auto-accept invoked without existing_journal_entry id "
                f"(bank_tx={bank_tx.id})"
            )

        with db_transaction.atomic():
            recon = Reconciliation.objects.create(
                company_id=self.company_id,
                status="matched",
                reference=f"agent:{bank_tx.id}",
                notes=(
                    f"Auto-accepted by reconciliation agent. "
                    f"confidence={suggestion.get('confidence_score')} "
                    f"similarity={suggestion.get('similarity')} "
                    f"amount_match={suggestion.get('amount_match_score')}"
                ),
            )
            recon.bank_transactions.set([bank_tx])
            recon.journal_entries.set([je_id])

            BankTransaction.objects.filter(id=bank_tx.id).update(
                balance_validated=True
            )
            JournalEntry.objects.filter(id=je_id).update(is_reconciled=True)

        return recon.id

    def _bump_cache_version(self) -> None:
        """Invalidate the report cache after a batch of accepts. The
        per-row ``QuerySet.update()`` calls bypass ``auto_now``; the cache
        fingerprint won't move on its own. Best-effort."""
        try:
            from accounting.services.report_cache import bump_version

            bump_version(self.company_id)
        except Exception:  # pragma: no cover — cache hiccup must never block
            log.warning("report_cache.bump_version failed", exc_info=True)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _open_run(
        self,
        *,
        bank_account_id: int | None,
        date_from: date | None,
        date_to: date | None,
        bank_tx_limit: int | None,
    ) -> ReconciliationAgentRun:
        return ReconciliationAgentRun.objects.create(
            company_id=self.company_id,
            status="running",
            auto_accept_threshold=self.auto_accept_threshold,
            ambiguity_gap=self.ambiguity_gap,
            min_confidence=self.min_confidence,
            dry_run=self.dry_run,
            bank_account_id=bank_account_id,
            date_from=date_from,
            date_to=date_to,
            bank_tx_limit=bank_tx_limit,
            triggered_by=self.triggered_by,
            triggered_by_user_id=self.triggered_by_user_id,
        )

    def _close_run(
        self,
        run: ReconciliationAgentRun,
        result: AgentRunResult,
        *,
        status: str,
        error_message: str = "",
    ) -> None:
        run.status = status
        run.finished_at = timezone.now()
        run.n_candidates = result.n_candidates
        run.n_auto_accepted = result.n_auto_accepted
        run.n_ambiguous = result.n_ambiguous
        run.n_no_match = result.n_no_match + result.n_not_applicable
        run.n_errors = result.n_errors
        if error_message:
            run.error_message = error_message[:4000]
        run.save(update_fields=[
            "status", "finished_at", "n_candidates", "n_auto_accepted",
            "n_ambiguous", "n_no_match", "n_errors", "error_message",
            "updated_at",
        ])

    def _record_decision(
        self,
        *,
        run: ReconciliationAgentRun,
        bank_tx: BankTransaction,
        outcome: str,
        top: Decimal | None,
        second: Decimal | None,
        suggestion_payload: dict[str, Any],
        reconciliation_id: int | None = None,
        error_message: str = "",
    ) -> ReconciliationAgentDecision:
        kwargs: dict[str, Any] = dict(
            company_id=self.company_id,
            run=run,
            bank_transaction=bank_tx,
            outcome=outcome,
            top_confidence=top,
            second_confidence=second,
            suggestion_payload=suggestion_payload or {},
            error_message=error_message[:4000],
        )
        if reconciliation_id is not None:
            kwargs["reconciliation_id"] = reconciliation_id
        return ReconciliationAgentDecision.objects.create(**kwargs)

    # ------------------------------------------------------------------
    # Candidate selection
    # ------------------------------------------------------------------
    def _candidate_bank_transactions(
        self,
        *,
        bank_account_id: int | None,
        date_from: date | None,
        date_to: date | None,
        limit: int | None,
    ) -> list[BankTransaction]:
        qs = BankTransaction.objects.filter(company_id=self.company_id)
        # Exclude BankTx that already have any reconciliation — even pending
        # ones — to avoid the agent stepping on top of a workflow the
        # operator has already started. The matched/approved subset would
        # also work for the "double-match" guard but would let the agent
        # auto-accept on top of a manually-pending row, which is confusing.
        qs = qs.exclude(reconciliations__isnull=False)
        if bank_account_id:
            qs = qs.filter(bank_account_id=bank_account_id)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        qs = qs.order_by("-date")
        if limit:
            qs = qs[:limit]
        return list(qs)

    # ------------------------------------------------------------------
    # Suggestion-result unpacking
    # ------------------------------------------------------------------
    @staticmethod
    def _unpack_suggestions(wrapped: dict[str, Any], bank_tx_id: int) -> list[dict[str, Any]]:
        """Pull the per-bank-tx suggestion list out of the wrapper payload
        returned by :meth:`BankTransactionSuggestionService.suggest_book_transactions`.

        Wrapper shape::

            {
              "suggestions": [
                {"bank_transaction_id": 1, "suggestions": [<sug1>, <sug2>, ...]},
                ...
              ],
              "errors": [...],
            }
        """
        for entry in wrapped.get("suggestions") or []:
            if entry.get("bank_transaction_id") == bank_tx_id:
                return list(entry.get("suggestions") or [])
        return []

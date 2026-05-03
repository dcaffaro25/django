# -*- coding: utf-8 -*-
"""
Operations / Data-health check service.

A registry of pluggable checks that surface "should-auto-update but
isn't" pipeline gaps -- the kind of issue that hides behind otherwise
clean-looking reports until someone goes looking.

Each check returns a ``HealthCheckResult`` with a count, severity,
small sample, and an optional CTA the frontend wires to a fix.

Adding a new check:
    1. Write a function ``check_<thing>(company) -> HealthCheckResult``.
    2. Register it in ``ALL_CHECKS``.
    3. ``run_health_checks(company)`` aggregates them and the
       /api/operacao/health-checks/ endpoint returns the lot.

Keeping checks pure and side-effect-free is intentional: the dashboard
calls this on every page load and we don't want to mutate state from a
read.

V1 checks (this file):
    * unposted_transactions   -- Tx.is_posted=False
    * stale_invoice_status    -- Invoice.status not derived from recon
    * unmatched_nfs           -- NFs with no accepted Tx link

Future checks worth adding:
    * unbalanced_transactions  (already in tx_status_service; promote)
    * stale_reconciliations    (bank tx unreconciled > 30 days)
    * orphan_product_services  (zero NF-item references in 90 days)
    * pending_suggestions_total  (cross-domain: BP groups, NF↔Tx,
      product groups, BP aliases)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as _date, timedelta
from decimal import Decimal
from typing import Callable, List, Optional

from django.db.models import Min, Q

logger = logging.getLogger(__name__)


SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_DANGER = "danger"


@dataclass
class HealthCheckResult:
    """One row of the dashboard."""
    key: str                          # stable; used as React key + i18n
    title: str                        # operator-readable name
    severity: str                     # info / warning / danger
    count: int                        # primary metric
    amount: Optional[str] = None      # optional R$ (Decimal-as-string)
    oldest_at: Optional[str] = None   # ISO date of oldest offender
    sample: List[dict] = field(default_factory=list)  # up to 5 examples
    cta_label: Optional[str] = None   # button text
    cta_action: Optional[str] = None  # action key (frontend dispatches)
    cta_url: Optional[str] = None     # deep-link URL (frontend navigates)
    hint: str = ""                    # one-line explanation
    notes: str = ""                   # caveats / methodology

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "severity": self.severity,
            "count": self.count,
            "amount": self.amount,
            "oldest_at": self.oldest_at,
            "sample": self.sample,
            "cta_label": self.cta_label,
            "cta_action": self.cta_action,
            "cta_url": self.cta_url,
            "hint": self.hint,
            "notes": self.notes,
        }


def _severity_by_age(oldest_days: Optional[int]) -> str:
    """Standard age → severity mapping reused by several checks."""
    if oldest_days is None:
        return SEVERITY_INFO
    if oldest_days >= 60:
        return SEVERITY_DANGER
    if oldest_days >= 30:
        return SEVERITY_WARNING
    return SEVERITY_INFO


# ---------------------------------------------------------------------
# Check 1: Unposted transactions
# ---------------------------------------------------------------------
def check_unposted_transactions(company) -> HealthCheckResult:
    """Tx with ``is_posted=False`` AND ``state != 'posted'``.

    On Evolat this is currently 100% of the catalog (5,845 / 5,845)
    -- a smoking gun that the posting pipeline is dormant or never
    flipped. Either way, the operator should know.
    """
    from accounting.models import Transaction

    qs = Transaction.objects.filter(
        company=company,
    ).filter(Q(is_posted=False) & ~Q(state="posted"))
    count = qs.count()
    oldest = qs.aggregate(d=Min("date")).get("d")
    today = _date.today()
    oldest_days = (today - oldest).days if oldest else None

    sample = list(
        qs.order_by("date", "id")
        .values("id", "date", "amount", "description")[:5]
    )
    sample_payload = [
        {
            "id": s["id"],
            "date": s["date"].isoformat() if s["date"] else None,
            "amount": str(s["amount"]) if s["amount"] is not None else None,
            "description": (s["description"] or "")[:80],
        }
        for s in sample
    ]

    severity = SEVERITY_INFO if count == 0 else _severity_by_age(oldest_days)
    if count > 0 and severity == SEVERITY_INFO:
        # Even fresh unposted Txs deserve a warning if there are any --
        # the question is whether *posting* is wired at all on this
        # tenant. ``danger`` is reserved for >60-day staleness.
        severity = SEVERITY_WARNING

    return HealthCheckResult(
        key="unposted_transactions",
        title="Transações sem posting",
        severity=severity,
        count=count,
        oldest_at=oldest.isoformat() if oldest else None,
        sample=sample_payload,
        cta_label="Investigar" if count > 0 else None,
        cta_url="/accounting/transactions?state=pending" if count > 0 else None,
        hint=(
            "Transações com ``is_posted=False`` ainda não foram lançadas no "
            "razão. Em tenants com posting automático, isto deve ser zero "
            "ou estar próximo de zero."
        ),
        notes=(
            "Pendentes (``state=pending``) podem ser intencionais até o "
            "fechamento do período. Se o pipeline de posting está "
            "configurado, conte e idade > 30d indicam stall."
        ),
    )


# ---------------------------------------------------------------------
# Check 2: Stale invoice status
# ---------------------------------------------------------------------
def check_stale_invoice_status(company) -> HealthCheckResult:
    """Open invoices whose linked NF↔Tx evidence shows they're paid.

    Wraps ``backfill_invoice_status_from_recon(dry_run=True)`` so the
    dashboard reads what the backfill button on /billing/faturas
    would do without any side-effects.
    """
    from billing.services.invoice_payment_evidence import (
        backfill_invoice_status_from_recon,
    )
    from billing.models import Invoice

    result = backfill_invoice_status_from_recon(company, dry_run=True)
    count = result["would_promote"]
    amount = result["promoted_amount"]

    # Oldest "would-promote" invoice as a freshness signal.
    oldest_at = None
    oldest_days = None
    if count > 0:
        oldest = (
            Invoice.objects
            .filter(
                company=company, invoice_type="sale",
                status__in=("issued", "partially_paid"),
            )
            .aggregate(d=Min("invoice_date"))
            .get("d")
        )
        oldest_at = oldest.isoformat() if oldest else None
        oldest_days = (_date.today() - oldest).days if oldest else None

    sample_payload = [
        {
            "id": s["invoice_id"],
            "invoice_number": s["invoice_number"],
            "amount": s["amount"],
            "old_status": s["old_status"],
        }
        for s in result["samples"]
    ]

    if count == 0:
        severity = SEVERITY_INFO
    elif Decimal(amount or 0) > Decimal("100000") or (oldest_days or 0) >= 60:
        severity = SEVERITY_DANGER
    else:
        severity = SEVERITY_WARNING

    return HealthCheckResult(
        key="stale_invoice_status",
        title="Faturas com status desatualizado",
        severity=severity,
        count=count,
        amount=str(amount) if amount else None,
        oldest_at=oldest_at,
        sample=sample_payload,
        cta_label="Aplicar backfill" if count > 0 else None,
        # The /billing/faturas page hosts the confirm modal; the
        # dashboard deep-links there with a hash flag the page picks
        # up to auto-open the modal.
        cta_url="/billing/faturas#backfill-status" if count > 0 else None,
        hint=(
            "Faturas em ``issued`` / ``partially_paid`` cujo Tx vinculado "
            "está conciliado -- evidência de que o caixa entrou e o "
            "status deveria estar ``paid``."
        ),
        notes=(
            "Resolva via botão ``Atualizar status`` na aba Faturas. O "
            "hook automático já mantém isto zero a partir de novos "
            "vínculos NF↔Tx aceitos."
        ),
    )


# ---------------------------------------------------------------------
# Check 3: Unmatched NFs
# ---------------------------------------------------------------------
def check_unmatched_nfs(
    company, *, age_days: int = 30,
) -> HealthCheckResult:
    """NFs older than ``age_days`` with no accepted ``NFTransactionLink``.

    Implies either the matcher missed them or no operator has reviewed
    the suggestions. Sales-side NFs (``tipo_operacao=1``,
    ``finalidade=1``) only -- devoluções have a different cash flow
    that's expected to look unmatched until the return is processed.
    """
    from billing.models import NotaFiscal, NFTransactionLink

    cutoff = _date.today() - timedelta(days=age_days)

    accepted_nf_ids = (
        NFTransactionLink.objects
        .filter(company=company, review_status="accepted")
        .values_list("nota_fiscal_id", flat=True)
    )
    qs = NotaFiscal.objects.filter(
        company=company,
        tipo_operacao=1,
        finalidade=1,
        data_emissao__date__lt=cutoff,
    ).exclude(id__in=list(accepted_nf_ids))

    count = qs.count()
    oldest = qs.aggregate(d=Min("data_emissao")).get("d")
    oldest_at = oldest.date().isoformat() if oldest else None
    oldest_days = (_date.today() - oldest.date()).days if oldest else None

    sample = list(
        qs.order_by("data_emissao")
        .values(
            "id", "numero", "data_emissao", "valor_nota",
            "dest_nome", "emit_nome",
        )[:5]
    )
    sample_payload = [
        {
            "id": s["id"],
            "numero": s["numero"],
            "date": s["data_emissao"].date().isoformat() if s["data_emissao"] else None,
            "amount": str(s["valor_nota"]) if s["valor_nota"] is not None else None,
            "counterparty": (s["dest_nome"] or s["emit_nome"] or "")[:60],
        }
        for s in sample
    ]

    severity = _severity_by_age(oldest_days) if count > 0 else SEVERITY_INFO

    return HealthCheckResult(
        key="unmatched_nfs",
        title=f"NFs sem vínculo de Tx (> {age_days}d)",
        severity=severity,
        count=count,
        oldest_at=oldest_at,
        sample=sample_payload,
        cta_label="Revisar vínculos" if count > 0 else None,
        cta_url="/billing/links?tab=suggested" if count > 0 else None,
        hint=(
            "NFs de venda (Saída + Normal) com mais de 30 dias sem nenhuma "
            "Tx aceita. Indica que o matcher não encontrou par ou que as "
            "sugestões não foram revisadas."
        ),
        notes=(
            "Devoluções (``finalidade=4``) são excluídas porque seguem "
            "fluxo de caixa diferente."
        ),
    )


# ---------------------------------------------------------------------
# Check 4: Unbalanced transactions
# ---------------------------------------------------------------------
def check_unbalanced_transactions(company) -> HealthCheckResult:
    """Tx where ``is_balanced=False``. Means debit ≠ credit on the
    JE rows -- a data integrity issue (the GL won't balance unless
    every Tx balances). Often surfaces import bugs or partial
    JE entry."""
    from accounting.models import Transaction

    qs = Transaction.objects.filter(
        company=company,
        is_balanced=False,
    ).exclude(state="canceled")
    count = qs.count()
    oldest = qs.aggregate(d=Min("date")).get("d")
    today = _date.today()
    oldest_days = (today - oldest).days if oldest else None

    sample = list(
        qs.order_by("date", "id")
        .values("id", "date", "amount", "description", "total_amount_discrepancy")[:5]
    )
    sample_payload = [
        {
            "id": s["id"],
            "date": s["date"].isoformat() if s["date"] else None,
            "amount": str(s["amount"]) if s["amount"] is not None else None,
            "discrepancy": str(s.get("total_amount_discrepancy") or 0),
            "description": (s["description"] or "")[:60],
        }
        for s in sample
    ]

    if count == 0:
        severity = SEVERITY_INFO
    elif (oldest_days or 0) >= 60 or count > 100:
        severity = SEVERITY_DANGER
    else:
        severity = SEVERITY_WARNING

    return HealthCheckResult(
        key="unbalanced_transactions",
        title="Transações desbalanceadas",
        severity=severity,
        count=count,
        oldest_at=oldest.isoformat() if oldest else None,
        sample=sample_payload,
        cta_label="Investigar" if count > 0 else None,
        cta_url="/accounting/transactions?is_balanced=false" if count > 0 else None,
        hint=(
            "Transações com soma de débitos diferente da soma de créditos. "
            "Indica entrada parcial de JEs (importação travada, edição "
            "manual incompleta) ou bug de pipeline."
        ),
        notes=(
            "O razão NÃO fecha enquanto houver Tx desbalanceada. Resolver "
            "manualmente caso a caso ou via importação corretiva."
        ),
    )


# ---------------------------------------------------------------------
# Check 5: Pending suggestions across the four review queues
# ---------------------------------------------------------------------
def check_pending_suggestions(company) -> HealthCheckResult:
    """Cross-domain suggestion-queue total: NF↔Tx links, BP groups,
    product groups, BP aliases, product aliases. A reminder that the
    review queues need attention; severity scales with total count
    so a small backlog is info, a large one is warning."""
    from billing.models import (
        BusinessPartnerAlias, BusinessPartnerGroupMembership,
        NFTransactionLink, ProductServiceAlias,
        ProductServiceGroupMembership,
    )

    counts = {
        "nf_tx_links": NFTransactionLink.objects.filter(
            company=company, review_status="suggested",
        ).count(),
        "bp_group_memberships": BusinessPartnerGroupMembership.objects.filter(
            company=company, review_status="suggested",
        ).count(),
        "ps_group_memberships": ProductServiceGroupMembership.objects.filter(
            company=company, review_status="suggested",
        ).count(),
        "bp_aliases": BusinessPartnerAlias.objects.filter(
            company=company, review_status="suggested",
        ).count(),
        "ps_aliases": ProductServiceAlias.objects.filter(
            company=company, review_status="suggested",
        ).count(),
    }
    total = sum(counts.values())

    sample_payload = [
        {"queue": q, "count": c}
        for q, c in counts.items() if c > 0
    ]

    if total == 0:
        severity = SEVERITY_INFO
    elif total > 500:
        severity = SEVERITY_DANGER
    elif total > 50:
        severity = SEVERITY_WARNING
    else:
        severity = SEVERITY_INFO

    # Pick the largest queue's deep-link as the primary CTA.
    cta_url = None
    cta_label = None
    if total > 0:
        biggest = max(counts.items(), key=lambda kv: kv[1])[0]
        if biggest == "nf_tx_links":
            cta_url = "/billing/links?tab=suggested"
        elif biggest in ("bp_group_memberships", "bp_aliases"):
            cta_url = "/billing/grupos"
        elif biggest == "ps_group_memberships":
            cta_url = "/billing/grupos"  # same hub, Produtos tab
        elif biggest == "ps_aliases":
            cta_url = "/billing/grupos"
        cta_label = "Revisar maior fila"

    return HealthCheckResult(
        key="pending_suggestions",
        title="Sugestões pendentes (todas as filas)",
        severity=severity,
        count=total,
        sample=sample_payload,
        cta_label=cta_label,
        cta_url=cta_url,
        hint=(
            "Soma dos itens em ``review_status=suggested`` em todas as "
            "filas curadas pelo operador (NF↔Tx, grupos de parceiros, "
            "grupos de produtos, apelidos)."
        ),
        notes=(
            "O detalhamento por fila aparece em ``sample``. Filas grandes "
            "podem indicar que a auto-promoção está conservadora demais "
            "ou que o operador não está revisando."
        ),
    )


# ---------------------------------------------------------------------
# Check 6: Stale bank transactions (unreconciled > 30 days)
# ---------------------------------------------------------------------
def check_stale_bank_transactions(
    company, *, age_days: int = 30,
) -> HealthCheckResult:
    """Bank transactions older than ``age_days`` not part of any
    closed (matched / approved) Reconciliation. Either the matcher
    hasn't found a counterpart or the operator hasn't approved the
    suggestion."""
    from accounting.models import BankTransaction, Reconciliation

    cutoff = _date.today() - timedelta(days=age_days)
    closed_recon_bt_ids = (
        Reconciliation.objects
        .filter(
            company=company,
            status__in=("matched", "approved"),
            is_deleted=False,
        )
        .values_list("bank_transactions__id", flat=True)
    )
    qs = BankTransaction.objects.filter(
        company=company,
        is_deleted=False,
        date__lt=cutoff,
    ).exclude(id__in=list(set(closed_recon_bt_ids)))

    count = qs.count()
    oldest = qs.aggregate(d=Min("date")).get("d")
    oldest_at = oldest.isoformat() if oldest else None
    oldest_days = (_date.today() - oldest).days if oldest else None

    sample = list(
        qs.order_by("date", "id")
        .values("id", "date", "amount", "description")[:5]
    )
    sample_payload = [
        {
            "id": s["id"],
            "date": s["date"].isoformat() if s["date"] else None,
            "amount": str(s["amount"]) if s["amount"] is not None else None,
            "description": (s["description"] or "")[:60],
        }
        for s in sample
    ]

    severity = _severity_by_age(oldest_days) if count > 0 else SEVERITY_INFO

    return HealthCheckResult(
        key="stale_bank_transactions",
        title=f"Bancárias não conciliadas (> {age_days}d)",
        severity=severity,
        count=count,
        oldest_at=oldest_at,
        sample=sample_payload,
        cta_label="Abrir bancada" if count > 0 else None,
        cta_url="/recon/workbench" if count > 0 else None,
        hint=(
            "BankTransactions com mais de 30 dias sem fazer parte de "
            "uma Reconciliation matched/approved. Indica acúmulo na fila "
            "do conciliador ou caixa que não está sendo casado com livro."
        ),
        notes=(
            "Soft-deletes excluídos. Use a Bancada (``/recon/workbench``) "
            "para revisar os candidatos do matcher e aceitar / rejeitar."
        ),
    )


# ---------------------------------------------------------------------
# Check 7: Orphan ProductService rows
# ---------------------------------------------------------------------
def check_orphan_product_services(
    company, *, age_days: int = 90,
) -> HealthCheckResult:
    """``ProductService`` rows with ``is_active=True`` that haven't
    been referenced by any ``NotaFiscalItem`` in the last ``age_days``.
    Cleanup hint, not an integrity issue: catalog rot accumulates as
    SKUs go end-of-life but the active flag never flips.

    Guard: if the tenant has zero NFs in the window at all, the
    "0 references" finding is meaningless — surface that as info+0
    rather than tagging every active product as orphan. The
    ``check_no_recent_nf_imports`` check covers the import-stalled
    case directly.
    """
    from billing.models import ProductService
    from billing.models_nfe import NotaFiscal, NotaFiscalItem

    cutoff = _date.today() - timedelta(days=age_days)
    has_recent_nfs = NotaFiscal.objects.filter(
        company=company,
        data_emissao__date__gte=cutoff,
    ).exists()
    if not has_recent_nfs:
        return HealthCheckResult(
            key="orphan_product_services",
            title=f"Produtos sem movimentação ({age_days}d)",
            severity=SEVERITY_INFO,
            count=0,
            hint=(
                "Sem NFs nos últimos 90 dias para basear a checagem. "
                "Veja ``no_recent_nf_imports`` para o pipeline de "
                "importação."
            ),
            notes="",
        )
    referenced_ids = (
        NotaFiscalItem.objects
        .filter(
            company=company,
            nota_fiscal__data_emissao__date__gte=cutoff,
        )
        .values_list("produto_id", flat=True)
        .distinct()
    )
    qs = ProductService.objects.filter(
        company=company, is_active=True,
    ).exclude(id__in=list(set(filter(None, referenced_ids))))

    count = qs.count()
    sample = list(
        qs.order_by("name")[:5].values("id", "code", "name", "item_type")
    )
    sample_payload = [
        {
            "id": s["id"],
            "code": s["code"],
            "name": (s["name"] or "")[:60],
            "type": s["item_type"],
        }
        for s in sample
    ]

    # Always informational -- this is cleanup, not an integrity issue.
    severity = SEVERITY_INFO
    if count > 200:
        severity = SEVERITY_WARNING

    return HealthCheckResult(
        key="orphan_product_services",
        title=f"Produtos sem movimentação ({age_days}d)",
        severity=severity,
        count=count,
        sample=sample_payload,
        cta_label="Listar produtos" if count > 0 else None,
        cta_url="/billing/produtos?is_active=true" if count > 0 else None,
        hint=(
            "Produtos / serviços ativos que não aparecem em nenhum item "
            "de NF nos últimos 90 dias. Considere desativar para reduzir "
            "ruído no catálogo."
        ),
        notes=(
            "Não é integridade -- só housekeeping. Produtos de catálogo "
            "sazonal ou que ainda não tiveram primeira venda também caem "
            "aqui. Revise antes de desativar em massa."
        ),
    )


# ---------------------------------------------------------------------
# Check 8: Latest NF import age
# ---------------------------------------------------------------------
def check_no_recent_nf_imports(company, *, fresh_days: int = 7) -> HealthCheckResult:
    """How long since the most recent NF was imported?

    Tenants on a live SEFAZ feed expect a few NFs / day. A gap of
    >7 days is a good early warning that the import pipeline (XML
    drop folder, SEFAZ poll, partner integration) is stuck.
    """
    from billing.models import NotaFiscal
    from django.db.models import Max

    latest = (
        NotaFiscal.objects
        .filter(company=company)
        .aggregate(d=Max("data_emissao")).get("d")
    )
    if latest is None:
        return HealthCheckResult(
            key="no_recent_nf_imports",
            title="Importação de NF",
            severity=SEVERITY_INFO,
            count=0,
            hint="Nenhuma NF importada ainda neste tenant.",
        )

    today = _date.today()
    days_since = (today - latest.date()).days

    if days_since <= fresh_days:
        severity = SEVERITY_INFO
    elif days_since <= 30:
        severity = SEVERITY_WARNING
    else:
        severity = SEVERITY_DANGER

    return HealthCheckResult(
        key="no_recent_nf_imports",
        title="Importação de NF",
        severity=severity,
        # ``count`` is days-since here -- the dashboard renders it as
        # the headline metric and the title carries the meaning.
        count=days_since,
        oldest_at=latest.date().isoformat(),
        hint=(
            f"Última NF importada há {days_since} dias. Se o pipeline "
            "está vivo, isto deveria ser ≤ alguns dias."
        ),
        cta_label="Abrir importações" if severity != SEVERITY_INFO else None,
        cta_url="/imports" if severity != SEVERITY_INFO else None,
        notes=(
            "Use a aba Importações para ver tarefas em fila ou erros. "
            "Em test/staging tenants este check pode ficar vermelho "
            "permanentemente; ignore conforme o caso."
        ),
    )


# ---------------------------------------------------------------------
# Registry + driver
# ---------------------------------------------------------------------
ALL_CHECKS: List[Callable[..., HealthCheckResult]] = [
    check_unposted_transactions,
    check_unbalanced_transactions,
    check_stale_invoice_status,
    check_unmatched_nfs,
    check_stale_bank_transactions,
    check_pending_suggestions,
    check_no_recent_nf_imports,
    check_orphan_product_services,
]


def run_health_checks(company) -> dict:
    """Run every registered check; return aggregated payload.

    Each check is independently try/excepted so one failure doesn't
    blank the dashboard. Failures show up as a separate row with a
    ``danger`` severity and the exception in ``notes``.
    """
    from django.utils import timezone

    results: List[dict] = []
    for fn in ALL_CHECKS:
        try:
            res = fn(company)
            results.append(res.to_dict())
        except Exception as exc:
            logger.exception(
                "health_check_service: %s failed for company_id=%s",
                fn.__name__, company.id,
            )
            results.append(HealthCheckResult(
                key=fn.__name__,
                title=fn.__name__.replace("check_", "").replace("_", " ").title(),
                severity=SEVERITY_DANGER,
                count=0,
                hint="Falha ao executar check.",
                notes=f"{type(exc).__name__}: {exc}",
            ).to_dict())

    # Headline: number of checks at each severity. Lets the page show
    # a single chip in the topbar without re-walking the array.
    by_severity = {SEVERITY_INFO: 0, SEVERITY_WARNING: 0, SEVERITY_DANGER: 0}
    for r in results:
        sev = r.get("severity", SEVERITY_INFO)
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "as_of": timezone.now().isoformat(),
        "tenant_subdomain": company.subdomain,
        "tenant_name": company.name,
        "checks": results,
        "by_severity": by_severity,
        "n_checks": len(results),
    }

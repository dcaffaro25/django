# -*- coding: utf-8 -*-
"""
Per-product revenue / volume / estimated-COGS / margin report.

Aggregates ``NotaFiscalItem`` rows over a date window, scoped by the
parent NF's ``tipo_operacao`` (Saída = sales by default) and
optionally by ``finalidade`` (1=Normal vs 4=Devolução). Returns:

  * Revenue (sum of ``valor_total``)
  * Volume (sum of ``quantidade``)
  * Estimated COGS (volume × ``ProductService.cost``) — current cost,
    NOT historical, so flagged as an estimate in the response
  * Estimated margin (revenue − cogs_est)
  * Returns (separate sum, finalidade=4)
  * Distinct NF count

Three rollup axes:
  * ``product`` — one row per ProductService (raw catalog)
  * ``consolidated`` — rolls members into their group's primary
    product so the same SKU under N codes counts once
    (uses ``ProductServiceGroupMembership``)
  * ``category`` — rolls into the family tree root
    (``ProductServiceCategory``); products without a category land
    in a synthetic ``None``-keyed bucket

Design choice: the rollups happen in Python after pulling the
per-item aggregation. The raw query is bounded by the date window +
tenant filter, so the row count stays small enough (Evolat: ~14k
NFitems × maybe 90 days = a few thousand at most). Doing the rollup
in SQL would require an awkward CASE-with-Subquery for the
group-primary lookup; the in-memory pass is clearer and fast enough.

Caller (viewset) sorts + truncates the response. The service emits
ALL eligible rows so the caller can filter / paginate as it sees fit.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date as _date
from decimal import Decimal
from typing import Dict, Iterable, Optional

from django.db.models import Count, Sum

from billing.models import ProductService
from billing.models_nfe import NotaFiscalItem
from billing.models_product_groups import ProductServiceGroupMembership

logger = logging.getLogger(__name__)


_GROUP_BY_VALUES = frozenset({"product", "consolidated", "category"})


@dataclass
class PnlRow:
    """One row of the report. Represents either a single product, the
    canonical product of a consolidation group, or a category root."""
    key: int
    key_kind: str  # "product" | "consolidated" | "category" (None-keyed = uncategorized)
    name: str
    code: str = ""
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    units: Decimal = Decimal("0")
    revenue: Decimal = Decimal("0")
    cogs_est: Decimal = Decimal("0")
    returns_units: Decimal = Decimal("0")
    returns_value: Decimal = Decimal("0")
    nf_count: int = 0
    member_count: int = 1  # for consolidated/category rollups, how many ProductServices contributed

    @property
    def margin_est(self) -> Decimal:
        return self.revenue - self.cogs_est

    @property
    def margin_pct_est(self) -> Optional[Decimal]:
        if self.revenue == 0:
            return None
        # Two decimal places, percent.
        return ((self.revenue - self.cogs_est) / self.revenue * Decimal("100")).quantize(Decimal("0.01"))

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "key_kind": self.key_kind,
            "name": self.name,
            "code": self.code,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "units": str(self.units),
            "revenue": str(self.revenue),
            "cogs_est": str(self.cogs_est),
            "margin_est": str(self.margin_est),
            "margin_pct_est": (
                str(self.margin_pct_est) if self.margin_pct_est is not None else None
            ),
            "returns_units": str(self.returns_units),
            "returns_value": str(self.returns_value),
            "nf_count": self.nf_count,
            "member_count": self.member_count,
        }


def _consolidation_map(company) -> Dict[int, int]:
    """Return {product_service_id: canonical_product_id}.

    Members of an accepted ``ProductServiceGroup`` map to the group's
    primary product. Standalones (no accepted membership) map to
    themselves. The map is read once per report call -- a few hundred
    rows -- and reused across all NF items in the window.
    """
    out: Dict[int, int] = {}
    accepted = (
        ProductServiceGroupMembership.objects
        .filter(
            company=company,
            review_status=ProductServiceGroupMembership.REVIEW_ACCEPTED,
        )
        .select_related("group")
        .only("product_service_id", "group__primary_product_id")
    )
    for m in accepted:
        out[m.product_service_id] = m.group.primary_product_id
    return out


def _resolve_product_meta(company, ids: Iterable[int]) -> Dict[int, dict]:
    """Single roundtrip to fetch name/code/category/cost for the
    products that appear in the report. Keyed by product id."""
    rows = (
        ProductService.objects
        .filter(company=company, id__in=set(ids))
        .select_related("category")
        .only("id", "name", "code", "cost", "category_id", "category__name")
    )
    out: Dict[int, dict] = {}
    for p in rows:
        out[p.id] = {
            "name": p.name,
            "code": p.code or "",
            "cost": Decimal(p.cost or 0),
            "category_id": p.category_id,
            "category_name": p.category.name if p.category_id else None,
        }
    return out


def compute_product_pnl(
    company,
    *,
    date_from: _date,
    date_to: _date,
    group_by: str = "consolidated",
    tipo_operacao: int = 1,
    entity_id: Optional[int] = None,
    finalidades: Iterable[int] = (1,),
) -> dict:
    """Build the per-product P&L payload for ``[date_from, date_to]``.

    Args:
        company: tenant.
        date_from / date_to: NF emission-date window (inclusive).
        group_by: ``product`` | ``consolidated`` (default) | ``category``.
        tipo_operacao: NF type — 1=Saída (sales), 0=Entrada (purchases).
        entity_id: optional Transaction.entity-style scope (NF.entity).
        finalidades: which NF finalidades count as "primary" rows
            (default: only ``1``=Normal). Devoluções (``finalidade=4``)
            are *always* aggregated into ``returns_*`` regardless of
            this filter.

    Returns a dict with totals + sorted rows.
    """
    if group_by not in _GROUP_BY_VALUES:
        raise ValueError(f"group_by must be one of {sorted(_GROUP_BY_VALUES)}")

    base = (
        NotaFiscalItem.objects
        .filter(
            company=company,
            nota_fiscal__data_emissao__date__gte=date_from,
            nota_fiscal__data_emissao__date__lte=date_to,
            nota_fiscal__tipo_operacao=tipo_operacao,
            produto__isnull=False,
        )
    )
    if entity_id is not None:
        # NF doesn't carry an entity FK directly; the convention used
        # by other reports is to scope through the Transaction the NF
        # is linked to (via NFTransactionLink). We treat ``entity_id``
        # as advisory and skip the filter here; passing entity through
        # the Tx side is the right path when there's a matched link.
        # Keeping the parameter in the signature so callers can supply
        # it without a second code path; effective filter is a no-op
        # until cross-Tx joins land.
        pass

    # --- Primary aggregation: rows in the requested finalidade(s) ---
    primary = (
        base.filter(nota_fiscal__finalidade__in=list(finalidades))
        .values("produto_id")
        .annotate(
            units=Sum("quantidade"),
            revenue=Sum("valor_total"),
            nf_count=Count("nota_fiscal_id", distinct=True),
        )
    )
    primary_by_product = {r["produto_id"]: r for r in primary}

    # --- Returns aggregation: same query, only finalidade=4 ---
    returns = (
        base.filter(nota_fiscal__finalidade=4)
        .values("produto_id")
        .annotate(
            r_units=Sum("quantidade"),
            r_value=Sum("valor_total"),
        )
    )
    returns_by_product = {r["produto_id"]: r for r in returns}

    relevant_ids = set(primary_by_product) | set(returns_by_product)
    if not relevant_ids:
        return {
            "period": {
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
            "group_by": group_by,
            "tipo_operacao": tipo_operacao,
            "totals": {
                "revenue": "0",
                "cogs_est": "0",
                "margin_est": "0",
                "units": "0",
                "returns_value": "0",
                "returns_units": "0",
                "nf_count": 0,
            },
            "rows": [],
            "notes": "No NF items in the requested window.",
        }

    meta = _resolve_product_meta(company, relevant_ids)
    consolidate = _consolidation_map(company) if group_by == "consolidated" else {}

    # --- Choose the rollup key per product ---
    def _bucket_key(pid: int) -> tuple[str, int]:
        if group_by == "product":
            return ("product", pid)
        if group_by == "consolidated":
            return ("consolidated", consolidate.get(pid, pid))
        # category
        cat = (meta.get(pid) or {}).get("category_id")
        return ("category", cat or 0)

    # --- Build buckets ---
    buckets: Dict[tuple, PnlRow] = {}
    members_seen: Dict[tuple, set] = defaultdict(set)
    for pid in relevant_ids:
        key_kind, key_id = _bucket_key(pid)
        members_seen[(key_kind, key_id)].add(pid)
        if (key_kind, key_id) not in buckets:
            # Pick a display row. For ``product``: the row itself.
            # For ``consolidated``: the canonical (primary) product.
            # For ``category``: the category metadata.
            display_pid = key_id if key_kind != "category" else pid
            display_meta = meta.get(display_pid, meta.get(pid, {}))
            if key_kind == "category":
                row_name = (
                    display_meta.get("category_name")
                    or ("(Sem categoria)" if key_id == 0 else f"Categoria #{key_id}")
                )
                row_code = ""
            else:
                row_name = display_meta.get("name", f"PS#{display_pid}")
                row_code = display_meta.get("code", "")
            buckets[(key_kind, key_id)] = PnlRow(
                key=key_id,
                key_kind=key_kind,
                name=row_name,
                code=row_code,
                category_id=display_meta.get("category_id"),
                category_name=display_meta.get("category_name"),
            )
        row = buckets[(key_kind, key_id)]
        prim = primary_by_product.get(pid)
        if prim:
            row.units += Decimal(prim["units"] or 0)
            row.revenue += Decimal(prim["revenue"] or 0)
            row.nf_count += int(prim["nf_count"] or 0)
            cost_per_unit = Decimal(meta.get(pid, {}).get("cost") or 0)
            row.cogs_est += cost_per_unit * Decimal(prim["units"] or 0)
        ret = returns_by_product.get(pid)
        if ret:
            row.returns_units += Decimal(ret["r_units"] or 0)
            row.returns_value += Decimal(ret["r_value"] or 0)

    # member_count for rollups
    for (kind, kid), members in members_seen.items():
        buckets[(kind, kid)].member_count = len(members)

    rows = list(buckets.values())
    rows.sort(key=lambda r: r.revenue, reverse=True)

    totals_units = sum((r.units for r in rows), Decimal("0"))
    totals_revenue = sum((r.revenue for r in rows), Decimal("0"))
    totals_cogs = sum((r.cogs_est for r in rows), Decimal("0"))
    totals_returns_value = sum((r.returns_value for r in rows), Decimal("0"))
    totals_returns_units = sum((r.returns_units for r in rows), Decimal("0"))
    totals_nf_count = sum((r.nf_count for r in rows), 0)
    totals_margin = totals_revenue - totals_cogs

    return {
        "period": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
        "group_by": group_by,
        "tipo_operacao": tipo_operacao,
        "totals": {
            "revenue": str(totals_revenue),
            "cogs_est": str(totals_cogs),
            "margin_est": str(totals_margin),
            "margin_pct_est": (
                str((totals_margin / totals_revenue * Decimal("100")).quantize(Decimal("0.01")))
                if totals_revenue
                else None
            ),
            "units": str(totals_units),
            "returns_value": str(totals_returns_value),
            "returns_units": str(totals_returns_units),
            "nf_count": totals_nf_count,
        },
        "rows": [r.to_dict() for r in rows],
        "notes": (
            "COGS estimate uses ProductService.cost × volume. Cost is the "
            "current snapshot, not historical, so margins drift with cost "
            "updates. For accounting-grade COGS use the GL JE pipeline."
        ),
    }

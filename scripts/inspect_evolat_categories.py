"""Drill into Evolat: per category, list accounts + their pending
JE delta. Goal: explain why ``receita_bruta`` reads R$ 0,00 in the
DRE even with include_pending on.
"""
from collections import defaultdict
from decimal import Decimal
from django.db.models import Sum, F, Value, DecimalField
from django.db.models.functions import Coalesce

from accounting.models import Account, JournalEntry
from accounting.services.taxonomy_resolver import effective_category
from multitenancy.models import Company

evolat = Company.objects.get(subdomain="evolat")
accounts = list(Account.objects.filter(company=evolat).select_related("parent"))
zero = Value(Decimal("0"), output_field=DecimalField())

# Per-account pending delta and posted delta.
pending_qs = (
    JournalEntry.objects.filter(account__company=evolat, state="pending")
    .values("account_id")
    .annotate(
        total=Sum(
            Coalesce(F("debit_amount"), zero) - Coalesce(F("credit_amount"), zero)
        ),
        n=Sum(Value(1, output_field=DecimalField())),
    )
)
pending_by_acc = {r["account_id"]: (r["total"] or Decimal("0"), int(r["n"] or 0)) for r in pending_qs}

# Group accounts by effective_category and dump the rows.
by_cat = defaultdict(list)
for a in accounts:
    cat = effective_category(a) or "<uncategorized>"
    by_cat[cat].append(a)

# Categories the DRE/Balanço math reads from.
DRE_CATS = [
    "receita_bruta",
    "deducao_receita",
    "custo",
    "despesa_operacional",
    "receita_financeira",
    "despesa_financeira",
    "outras_receitas",
    "imposto_sobre_lucro",
]
BAL_CATS = [
    "ativo_circulante",
    "ativo_nao_circulante",
    "passivo_circulante",
    "passivo_nao_circulante",
    "patrimonio_liquido",
]

# Show DRE categories with their accounts + pending volume.
for cat in DRE_CATS + BAL_CATS:
    rows = by_cat.get(cat, [])
    n_with_je = sum(1 for a in rows if a.id in pending_by_acc)
    total_pending = sum(
        (pending_by_acc.get(a.id, (Decimal("0"), 0))[0] for a in rows),
        Decimal("0"),
    )
    print(f"\n[{cat}]  accounts={len(rows)}  with-JE={n_with_je}  pending-delta={total_pending:.2f}")
    for a in rows:
        d, n = pending_by_acc.get(a.id, (Decimal("0"), 0))
        if n == 0:
            continue
        print(f"   id={a.id:>5}  n_je={n:>4}  delta={d:>15,.2f}  level={a.level}  name={a.name}")

# Anything that has JE volume but uncategorized?
uncategorized_with_je = []
for a in accounts:
    if a.id in pending_by_acc:
        cat = effective_category(a)
        if not cat:
            uncategorized_with_je.append((a, pending_by_acc[a.id]))
print(f"\n\nUNCATEGORIZED accounts with pending JEs: {len(uncategorized_with_je)}")
for a, (d, n) in uncategorized_with_je:
    print(f"   id={a.id:>5}  n_je={n:>4}  delta={d:>15,.2f}  name={a.name}  parent_id={a.parent_id}")

# Account 1591 / similar check: what's their JE volume vs balance?
print("\n\nSAMPLE: top 10 accounts by absolute pending delta")
ranked = sorted(pending_by_acc.items(), key=lambda kv: abs(kv[1][0]), reverse=True)[:10]
acc_by_id = {a.id: a for a in accounts}
for aid, (d, n) in ranked:
    a = acc_by_id.get(aid)
    if not a:
        continue
    cat = effective_category(a) or "<uncategorized>"
    print(f"   id={aid}  n_je={n}  delta={d:>15,.2f}  cat={cat}  name={a.name}")

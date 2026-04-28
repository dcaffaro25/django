"""One-off validation: aggregate Evolat's journal entries by
``effective_category`` and compare against what ``current_balance``
returns via the serializer (with and without ``include_pending``).

Run from the repo root:

    python manage.py shell < scripts/validate_dre_evolat.py
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
print(f"loaded {len(accounts)} accounts for evolat")

# Build {account_id -> effective_category} via the resolver. The resolver
# walks the parent chain looking for the nearest tagged ancestor; this is
# exactly what the API serializer does at request time.
cat_by_id = {}
for a in accounts:
    cat_by_id[a.id] = effective_category(a)

# Per-account JE aggregation: posted-only and pending-only (debit - credit).
zero = Value(Decimal("0"), output_field=DecimalField())
posted_qs = (
    JournalEntry.objects.filter(account__company=evolat, state="posted")
    .values("account_id")
    .annotate(
        total=Sum(
            Coalesce(F("debit_amount"), zero) - Coalesce(F("credit_amount"), zero)
        )
    )
)
pending_qs = (
    JournalEntry.objects.filter(account__company=evolat, state="pending")
    .values("account_id")
    .annotate(
        total=Sum(
            Coalesce(F("debit_amount"), zero) - Coalesce(F("credit_amount"), zero)
        )
    )
)
posted_by_acc = {row["account_id"]: row["total"] or Decimal("0") for row in posted_qs}
pending_by_acc = {row["account_id"]: row["total"] or Decimal("0") for row in pending_qs}

# Per-category sums, both modes. ``current_balance`` is per-account
# own-only (no descendant rollup), so summing every account in a
# category — parents AND leaves — does not double-count. The earlier
# "leaves only" rule silently dropped JEs booked to mid-tree parents
# (e.g. Evolat's "Venda De Produtos" level=3 with 4,342 pending JEs).
sum_posted_only = defaultdict(lambda: Decimal("0"))
sum_with_pending = defaultdict(lambda: Decimal("0"))
for a in accounts:
    cat = cat_by_id.get(a.id)
    if not cat:
        continue
    anchor = a.balance or Decimal("0")
    posted = posted_by_acc.get(a.id, Decimal("0"))
    pending = pending_by_acc.get(a.id, Decimal("0"))
    sum_posted_only[cat] += anchor + posted
    sum_with_pending[cat] += anchor + posted + pending

print("\n=== posted-only (anchor + posted) ===")
for c in sorted(sum_posted_only.keys()):
    print(f"  {c:30s} {sum_posted_only[c]:>20.2f}")

print("\n=== with pending (anchor + posted + pending) ===")
for c in sorted(sum_with_pending.keys()):
    print(f"  {c:30s} {sum_with_pending[c]:>20.2f}")

# DRE composition (matches the DreTab math in StandardReportsPage.tsx):
def dre(cats):
    g = lambda k: cats.get(k, Decimal("0"))
    receita_bruta = g("receita_bruta")
    deducoes = g("deducao_receita")
    receita_liquida = receita_bruta + deducoes
    custos = g("custo")
    lucro_bruto = receita_liquida + custos
    despesas_op = g("despesa_operacional")
    ebit = lucro_bruto + despesas_op
    receita_fin = g("receita_financeira")
    despesa_fin = g("despesa_financeira")
    resultado_fin = receita_fin + despesa_fin
    outras = g("outras_receitas")
    lair = ebit + resultado_fin + outras
    imposto = g("imposto_sobre_lucro")
    lucro_liq = lair + imposto
    return {
        "receita_bruta": receita_bruta,
        "deducoes": deducoes,
        "receita_liquida": receita_liquida,
        "custos": custos,
        "lucro_bruto": lucro_bruto,
        "despesas_op": despesas_op,
        "ebit": ebit,
        "resultado_fin": resultado_fin,
        "outras": outras,
        "lair": lair,
        "imposto": imposto,
        "lucro_liq": lucro_liq,
    }

print("\n=== DRE (posted-only) ===")
for k, v in dre(sum_posted_only).items():
    print(f"  {k:20s} {v:>20.2f}")
print("\n=== DRE (with pending) ===")
for k, v in dre(sum_with_pending).items():
    print(f"  {k:20s} {v:>20.2f}")

# Balanço composition
def balanco(cats):
    g = lambda k: cats.get(k, Decimal("0"))
    ativo_circ = g("ativo_circulante")
    ativo_nc = g("ativo_nao_circulante")
    total_ativo = ativo_circ + ativo_nc
    pass_circ = g("passivo_circulante")
    pass_nc = g("passivo_nao_circulante")
    pl = g("patrimonio_liquido")
    total_passivo_pl = pass_circ + pass_nc + pl
    return {
        "ativo_circ": ativo_circ,
        "ativo_nc": ativo_nc,
        "total_ativo": total_ativo,
        "pass_circ": pass_circ,
        "pass_nc": pass_nc,
        "pl": pl,
        "total_passivo_pl": total_passivo_pl,
        "diferenca": total_ativo - total_passivo_pl,
    }

print("\n=== Balanço (posted-only) ===")
for k, v in balanco(sum_posted_only).items():
    print(f"  {k:20s} {v:>20.2f}")
print("\n=== Balanço (with pending) ===")
for k, v in balanco(sum_with_pending).items():
    print(f"  {k:20s} {v:>20.2f}")

# Sanity: account-level coverage
n_categorized = sum(1 for v in cat_by_id.values() if v)
print(f"\ncategorized accounts: {n_categorized}/{len(accounts)}")

# Cross-check: total JE volume by state.
posted_total = sum(posted_by_acc.values(), Decimal("0"))
pending_total = sum(pending_by_acc.values(), Decimal("0"))
print(f"\nposted JE delta (sum debit-credit, all accounts): {posted_total:.2f}")
print(f"pending JE delta (sum debit-credit, all accounts): {pending_total:.2f}")

# JEs that aren't in (posted, pending) — are they affecting anything?
all_states = (
    JournalEntry.objects.filter(account__company=evolat)
    .values_list("state", flat=True)
    .distinct()
)
print(f"distinct JE states for evolat: {sorted(all_states)}")

"""
Per-model token pricing for cost estimation.

Rates are in **USD per 1,000 tokens**, per provider + model. Copied from the
providers' public pricing pages; they change occasionally — treat our
estimates as approximations, not billable amounts (the provider dashboard
is authoritative).

Last reviewed: 2026-01. When a new model ships, add an entry here and the
`AIUsageLog.estimated_cost_usd` column picks it up automatically.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, Tuple


# Dict[(provider, model)] -> (input_per_1k_usd, output_per_1k_usd)
_PRICING: Dict[Tuple[str, str], Tuple[Decimal, Decimal]] = {
    # --- OpenAI ---
    ("openai", "gpt-4o"):          (Decimal("0.0025"),  Decimal("0.01")),
    ("openai", "gpt-4o-mini"):     (Decimal("0.00015"), Decimal("0.0006")),
    ("openai", "gpt-4-turbo"):     (Decimal("0.01"),    Decimal("0.03")),
    ("openai", "gpt-4"):           (Decimal("0.03"),    Decimal("0.06")),
    ("openai", "gpt-3.5-turbo"):   (Decimal("0.0005"),  Decimal("0.0015")),
    # --- Anthropic ---
    ("anthropic", "claude-3-5-sonnet-20241022"): (Decimal("0.003"),   Decimal("0.015")),
    ("anthropic", "claude-3-5-sonnet"):          (Decimal("0.003"),   Decimal("0.015")),
    ("anthropic", "claude-3-opus-20240229"):     (Decimal("0.015"),   Decimal("0.075")),
    ("anthropic", "claude-3-haiku-20240307"):    (Decimal("0.00025"), Decimal("0.00125")),
}

# Fallback when we don't recognise the model — cheap safe default so the
# log row still gets a plausible number. Mark it with a `is_estimated_fallback`
# flag on the log row if you want stricter accounting later.
_FALLBACK: Tuple[Decimal, Decimal] = (Decimal("0.005"), Decimal("0.015"))


def estimate_cost_usd(
    *,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal:
    """Return the estimated USD cost for a single call."""
    key = (provider.lower(), model)
    rates = _PRICING.get(key) or _PRICING.get((provider.lower(), model.split("-20")[0])) or _FALLBACK
    in_rate, out_rate = rates
    cost = (
        (Decimal(prompt_tokens) / Decimal("1000")) * in_rate
        + (Decimal(completion_tokens) / Decimal("1000")) * out_rate
    )
    # Round to 6 decimal places — the model column supports this.
    return cost.quantize(Decimal("0.000001"))


def known_models() -> list[tuple[str, str]]:
    """For the admin / dashboard UI: every priced (provider, model) pair."""
    return sorted(_PRICING.keys())

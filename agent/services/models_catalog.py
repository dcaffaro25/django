"""Curated catalog of Codex models exposed to the frontend.

This is the source of truth for the model dropdown in the agent widget.
We don't auto-discover from OpenAI because the Codex API doesn't expose
a ``GET /models`` endpoint with the metadata we want (context window,
reasoning support, etc.) — and the slugs themselves are documented
elsewhere. Update the list as OpenAI ships new variants.

Numbers (``context_window``) are best-effort approximations from
public docs / community measurements; they're for UX only ("X / Y
tokens" hint), never used to enforce limits.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CodexModel:
    slug: str
    label: str
    description: str
    supports_reasoning: bool
    context_window: int   # approximate, for UI hint only


# Ordered: most-recommended first.
CODEX_MODELS: tuple[CodexModel, ...] = (
    CodexModel(
        slug="gpt-5.5",
        label="GPT-5.5",
        description="Recomendado: melhor para raciocínio complexo e tarefas com muitas ferramentas.",
        supports_reasoning=True,
        context_window=400_000,
    ),
    CodexModel(
        slug="gpt-5.4",
        label="GPT-5.4",
        description="Default do Codex CLI. Equilíbrio entre custo e qualidade.",
        supports_reasoning=True,
        context_window=256_000,
    ),
    CodexModel(
        slug="gpt-5.4-mini",
        label="GPT-5.4 Mini",
        description="Mais rápido e barato, para perguntas simples.",
        supports_reasoning=False,
        context_window=128_000,
    ),
    CodexModel(
        slug="gpt-5.3-codex",
        label="GPT-5.3 Codex",
        description="Especialista em código. Útil quando o agente analisa lógica fiscal complexa.",
        supports_reasoning=True,
        context_window=192_000,
    ),
    CodexModel(
        slug="gpt-5.3-codex-spark",
        label="GPT-5.3 Codex Spark (preview)",
        description="Iterações quase instantâneas. Disponível apenas em ChatGPT Pro.",
        supports_reasoning=False,
        context_window=128_000,
    ),
)

REASONING_EFFORTS: tuple[str, ...] = ("minimal", "low", "medium", "high")


def catalog_payload(*, default_model: str) -> dict:
    """Shape returned by :class:`agent.views.AgentModelsCatalogView`."""
    return {
        "default_model": default_model,
        "reasoning_efforts": list(REASONING_EFFORTS),
        "models": [asdict(m) for m in CODEX_MODELS],
    }


def supports_reasoning(slug: str) -> bool:
    """True iff sending ``reasoning: {effort}`` is valid for *slug*. Used
    by the runtime to silently drop reasoning args on models that don't
    accept them, instead of bubbling a 400."""
    for m in CODEX_MODELS:
        if m.slug == slug:
            return m.supports_reasoning
    # Unknown slug — assume yes; OpenAI will 400 if not, with a clear msg.
    return True

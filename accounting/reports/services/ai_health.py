"""Provider key health checks.

Pings each configured AI provider with a minimal request and reports
whether the shared key is valid, which model is active, and how long
the round-trip took. The result is cached for 5 minutes (keyed by
provider) so repeat page loads don't hammer the upstream APIs.

**Not logged** to :class:`AIUsageLog` — this is an admin infra check,
not a user-driven call. It should never show up in the per-user cost
attribution dashboard.

Ping strategy per provider:

* **OpenAI** — ``client.models.list()`` is free and fast, and returns
  401 on a bad key so we get a clean auth signal without spending any
  tokens.
* **Anthropic** — no public "list models" endpoint; we send a 1-token
  ``messages.create`` call (prompt="1", max_tokens=1). Costs ~1 in + 1
  out token per check, amortised by the cache.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from django.core.cache import cache

from accounting.services.external_ai_client import ExternalAIClient


log = logging.getLogger(__name__)


# Providers we know how to ping. Adding new providers is a matter of
# implementing a _ping_<provider> function below.
PROVIDERS: List[str] = ["openai", "anthropic"]

# Default cache window so repeat dashboard loads don't blast the API.
_CACHE_TTL_SECONDS = 5 * 60


def _cache_key(provider: str) -> str:
    return f"reports.ai.health.{provider}"


def check_provider(provider: str, *, force: bool = False) -> Dict[str, Any]:
    """Return the current health snapshot for one provider.

    Keys in the returned dict:

    - ``provider``      (str): the provider name (echoed)
    - ``configured``    (bool): whether a key is available in the fallback chain
    - ``status``        (str): ``"ok"`` | ``"error"`` | ``"not_configured"``
    - ``model``         (str | None): the model the client resolved to
    - ``latency_ms``    (int | None): round-trip time of the ping
    - ``error_type``    (str | None): exception class name on failure
    - ``error_message`` (str | None): short error string for the UI
    - ``checked_at``    (str | None): ISO-8601 timestamp when the ping ran
    - ``from_cache``    (bool): True when we returned a memoized result
    """
    ck = _cache_key(provider)
    if not force:
        cached = cache.get(ck)
        if cached is not None:
            return {**cached, "from_cache": True}

    result = _run_ping(provider)
    cache.set(ck, result, _CACHE_TTL_SECONDS)
    return {**result, "from_cache": False}


def check_all(*, force: bool = False) -> List[Dict[str, Any]]:
    """Check every known provider. Used by the dashboard cards."""
    return [check_provider(p, force=force) for p in PROVIDERS]


def _run_ping(provider: str) -> Dict[str, Any]:
    from datetime import datetime, timezone
    base: Dict[str, Any] = {
        "provider": provider,
        "configured": False,
        "status": "not_configured",
        "model": None,
        "latency_ms": None,
        "error_type": None,
        "error_message": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        client = ExternalAIClient(provider=provider)
    except Exception as exc:
        base["error_type"] = type(exc).__name__
        base["error_message"] = str(exc)[:200]
        base["status"] = "error"
        return base

    base["model"] = client.model
    if not client.api_key:
        # Leave status="not_configured" — UI shows a gray badge.
        return base
    base["configured"] = True

    t0 = time.time()
    try:
        if provider == "openai":
            _ping_openai(client)
        elif provider == "anthropic":
            _ping_anthropic(client)
        else:
            raise ValueError(f"no ping implementation for provider {provider!r}")
        base["latency_ms"] = int((time.time() - t0) * 1000)
        base["status"] = "ok"
    except Exception as exc:
        base["latency_ms"] = int((time.time() - t0) * 1000)
        base["status"] = "error"
        base["error_type"] = type(exc).__name__
        base["error_message"] = str(exc)[:200]
        log.warning("AI health ping failed for %s: %s", provider, exc)
    return base


def _ping_openai(client: ExternalAIClient) -> None:
    """Cheap auth check against OpenAI — list models, no tokens spent."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai SDK not installed") from exc
    oai = OpenAI(api_key=client.api_key, timeout=15.0)
    # iterating turns the SyncPage into a concrete request; we only need
    # the first page, so we cap by breaking after the first item.
    it = iter(oai.models.list())
    try:
        next(it)
    except StopIteration:
        # No models returned (unusual but not an auth failure).
        pass


def _ping_anthropic(client: ExternalAIClient) -> None:
    """Minimal auth check — send a 1-token prompt, throw away the reply."""
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("anthropic SDK not installed") from exc
    a = anthropic.Anthropic(api_key=client.api_key, timeout=15.0)
    a.messages.create(
        model=client.model,
        max_tokens=1,
        messages=[{"role": "user", "content": "1"}],
    )

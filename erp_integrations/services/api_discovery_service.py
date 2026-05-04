"""
URL-based API discovery — Phase 2 of the Sandbox API plan.

Operator pastes a URL → we try to identify the APIs the docs describe
and return structured candidates the operator can review and import as
``ERPAPIDefinition`` rows. Strategies in priority order:

1. ``openapi`` — try the URL as-is, plus a small set of well-known
   suffixes (``/swagger.json``, ``/openapi.json``, ``/v3/api-docs``).
   Parse the spec's ``paths`` → one candidate per (path, method).
   Highest confidence (1.0) when the spec parses cleanly.
2. ``postman`` — if the response looks like a Postman Collection
   (info.schema mentions postman.com), parse ``item[]`` → one
   candidate per leaf request. Confidence 0.9.
3. ``html`` — fallback: pull the page, sniff ``<code>``/``<pre>`` blocks
   for URL+JSON pairs. Heuristic, lower confidence (~0.4-0.6).
4. ``llm`` (opt-in) — when the tenant has set
   ``BillingTenantConfig.allow_llm_doc_parse``, send the page to a model
   with a strict JSON-output prompt. Output validated against a schema
   before becoming candidates.

Each candidate carries ``confidence`` ∈ [0,1], ``source_strategy``,
and a partial ``ERPAPIDefinition``-shaped dict ready to be POSTed to
``/api-definitions/`` (after the operator picks which to import).

The service is *pure* w.r.t. the Django models: it returns candidate
dicts, never persists. The viewset's ``import_selected`` action does
the writes.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)


# Conservative timeouts — discovery is interactive, the operator is
# waiting in front of a spinner. If a doc page is slow, fail fast.
HTTP_TIMEOUT_SECONDS = 10
HTTP_MAX_BYTES = 5 * 1024 * 1024  # 5MB — enough for any real spec / page

OPENAPI_SUFFIXES = (
    "",  # the URL as supplied
    "/swagger.json",
    "/openapi.json",
    "/v3/api-docs",
    "/api-docs",
)

# Strategy IDs (kept stable for the frontend filters).
STRATEGY_OPENAPI = "openapi"
STRATEGY_POSTMAN = "postman"
STRATEGY_HTML = "html"
STRATEGY_LLM = "llm"


@dataclass
class CandidateAPIDef:
    """One candidate ``ERPAPIDefinition`` produced by a discovery pass."""

    call: str
    method: str
    url: str
    description: str = ""
    param_schema: List[Dict[str, Any]] = field(default_factory=list)
    pagination_spec: Optional[Dict[str, Any]] = None
    records_path: str = ""
    auth_strategy: str = "provider_default"
    documentation_url: str = ""

    # Discovery metadata (not persisted to ERPAPIDefinition directly,
    # but shown in the UI so the operator can rank candidates).
    confidence: float = 0.5
    source_strategy: str = STRATEGY_HTML
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveryResult:
    """Full payload returned by ``discover_from_url``."""

    url: str
    strategies_tried: List[str] = field(default_factory=list)
    strategy_used: Optional[str] = None
    candidates: List[CandidateAPIDef] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "strategies_tried": self.strategies_tried,
            "strategy_used": self.strategy_used,
            "candidates": [c.to_dict() for c in self.candidates],
            "errors": self.errors,
        }


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------

def discover_from_url(
    url: str,
    *,
    allow_llm: bool = False,
    llm_caller: Optional[Any] = None,
) -> DiscoveryResult:
    """Try every strategy in priority order; return the first that
    yields ≥1 candidate. Falls through to the next on parse failure
    or empty result.

    ``allow_llm`` plus a non-None ``llm_caller`` enables the LLM-
    assisted parse as a final fallback. ``llm_caller`` is a callable
    ``(prompt: str, page_text: str) -> str`` returning JSON-only model
    output. Injected for testability — production code wires the real
    Anthropic SDK call here.
    """
    result = DiscoveryResult(url=url)

    if not url or not url.strip():
        result.errors.append({"strategy": "input", "message": "URL vazia."})
        return result

    # Strategy 1: OpenAPI -----------------------------------------
    result.strategies_tried.append(STRATEGY_OPENAPI)
    try:
        candidates = _try_openapi(url)
        if candidates:
            result.strategy_used = STRATEGY_OPENAPI
            result.candidates = candidates
            return result
    except Exception as exc:
        result.errors.append({"strategy": STRATEGY_OPENAPI, "message": str(exc)[:300]})

    # Strategy 2: Postman -----------------------------------------
    result.strategies_tried.append(STRATEGY_POSTMAN)
    try:
        candidates = _try_postman(url)
        if candidates:
            result.strategy_used = STRATEGY_POSTMAN
            result.candidates = candidates
            return result
    except Exception as exc:
        result.errors.append({"strategy": STRATEGY_POSTMAN, "message": str(exc)[:300]})

    # Strategy 3: HTML --------------------------------------------
    result.strategies_tried.append(STRATEGY_HTML)
    try:
        candidates = _try_html(url)
        if candidates:
            result.strategy_used = STRATEGY_HTML
            result.candidates = candidates
            # Don't return yet — give LLM a chance to do better when
            # enabled, since HTML is our weakest strategy.
            if not allow_llm:
                return result
    except Exception as exc:
        result.errors.append({"strategy": STRATEGY_HTML, "message": str(exc)[:300]})

    # Strategy 4: LLM (opt-in) ------------------------------------
    if allow_llm and llm_caller is not None:
        result.strategies_tried.append(STRATEGY_LLM)
        try:
            candidates = _try_llm(url, llm_caller=llm_caller)
            if candidates:
                # LLM beats HTML fallback only if HTML found nothing or
                # the LLM found more (heuristic — operator picks anyway).
                if not result.candidates or len(candidates) > len(result.candidates):
                    result.strategy_used = STRATEGY_LLM
                    result.candidates = candidates
        except Exception as exc:
            result.errors.append({"strategy": STRATEGY_LLM, "message": str(exc)[:300]})

    return result


# ---------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------

def _fetch(url: str, *, accept: str = "*/*") -> Tuple[int, Dict[str, str], bytes]:
    """Bounded fetch — caps body size and timeout. Returns
    ``(status, headers, body_bytes)``.
    """
    headers = {"Accept": accept, "User-Agent": "nord-api-discovery/1.0"}
    resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS, stream=True)
    chunks: List[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > HTTP_MAX_BYTES:
            raise ValueError(f"Response exceeded {HTTP_MAX_BYTES} bytes — refusing to parse.")
        chunks.append(chunk)
    body = b"".join(chunks)
    return resp.status_code, dict(resp.headers), body


# ---------------------------------------------------------------------
# Strategy 1: OpenAPI / Swagger
# ---------------------------------------------------------------------

def _try_openapi(url: str) -> List[CandidateAPIDef]:
    """Try the URL plus well-known suffixes; parse first one that
    looks like a valid OpenAPI / Swagger document.
    """
    import json

    last_err: Optional[str] = None
    for suffix in OPENAPI_SUFFIXES:
        candidate_url = url.rstrip("/") + suffix if suffix else url
        try:
            status, _, body = _fetch(candidate_url, accept="application/json")
            if status >= 400:
                last_err = f"{candidate_url} → HTTP {status}"
                continue
            spec = json.loads(body.decode("utf-8", errors="replace"))
        except (ValueError, UnicodeDecodeError) as exc:
            last_err = f"{candidate_url} → {exc}"
            continue
        except Exception as exc:
            last_err = f"{candidate_url} → {type(exc).__name__}: {exc}"
            continue

        if not isinstance(spec, dict):
            continue
        if "openapi" in spec or "swagger" in spec:
            return _parse_openapi_spec(spec, source_url=candidate_url)

    if last_err:
        logger.debug("OpenAPI discovery: no spec at any suffix. Last error: %s", last_err)
    return []


def _parse_openapi_spec(spec: Dict[str, Any], *, source_url: str) -> List[CandidateAPIDef]:
    """Walk ``paths`` and produce one candidate per (path, method)."""
    candidates: List[CandidateAPIDef] = []
    base_url = _openapi_base_url(spec, source_url)
    paths = spec.get("paths") or {}
    if not isinstance(paths, dict):
        return candidates

    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        # Path-level shared params apply to every method below.
        path_params = _coerce_param_schema(methods.get("parameters") or [])
        for method, op in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(op, dict):
                continue

            op_params = _coerce_param_schema(op.get("parameters") or [])
            body_params = _openapi_request_body_to_params(op.get("requestBody"))
            schema = _dedupe_params(path_params + op_params + body_params)

            full_url = (base_url.rstrip("/") + path) if base_url else path
            call = (
                op.get("operationId")
                or _slug_from_path(method, path)
            )
            description = (
                op.get("summary")
                or op.get("description")
                or ""
            )

            candidates.append(CandidateAPIDef(
                call=str(call)[:128],
                method=method.upper(),
                url=full_url,
                description=str(description)[:255],
                param_schema=schema,
                source_strategy=STRATEGY_OPENAPI,
                confidence=1.0,
                documentation_url=source_url,
                notes=f"From OpenAPI {spec.get('openapi') or spec.get('swagger') or '?'}.",
            ))
    return candidates


def _openapi_base_url(spec: Dict[str, Any], source_url: str) -> str:
    """Extract the first server URL or fall back to the doc URL's origin."""
    servers = spec.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict) and first.get("url"):
            base = first["url"]
            if base.startswith("/"):
                # Relative — anchor to source URL.
                p = urlparse(source_url)
                return f"{p.scheme}://{p.netloc}{base}"
            return base
    # Swagger 2.0
    if spec.get("host"):
        scheme = (spec.get("schemes") or ["https"])[0]
        host = spec["host"]
        base_path = spec.get("basePath", "")
        return f"{scheme}://{host}{base_path}"
    # Fallback: doc URL origin.
    p = urlparse(source_url)
    return f"{p.scheme}://{p.netloc}"


def _coerce_param_schema(params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert OpenAPI parameter objects to our param_schema rows."""
    out: List[Dict[str, Any]] = []
    for p in params:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        if not name:
            continue
        loc = p.get("in", "query")
        if loc not in ("body", "query", "path", "header"):
            loc = "query"
        schema = p.get("schema") or {}
        ptype = _openapi_type(schema.get("type"), schema.get("format"))
        out.append({
            "name": name,
            "type": ptype,
            "location": loc,
            "required": bool(p.get("required")),
            "description": (p.get("description") or "")[:255],
            "default": schema.get("default"),
        })
    return out


def _openapi_request_body_to_params(req_body: Any) -> List[Dict[str, Any]]:
    """Flatten an OpenAPI 3 requestBody to one body param per top-level
    field. Doesn't recurse — we report the top object name + leaves
    one level deep, which matches what the structured editor handles.
    """
    if not isinstance(req_body, dict):
        return []
    content = req_body.get("content") or {}
    if not isinstance(content, dict):
        return []
    # Prefer JSON.
    for ctype in ("application/json", *content.keys()):
        body = content.get(ctype)
        if not body:
            continue
        schema = (body or {}).get("schema") or {}
        if not isinstance(schema, dict):
            continue
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        if not isinstance(props, dict):
            return []
        out: List[Dict[str, Any]] = []
        for name, sub in props.items():
            if not isinstance(sub, dict):
                continue
            ptype = _openapi_type(sub.get("type"), sub.get("format"))
            out.append({
                "name": name,
                "type": ptype,
                "location": "body",
                "required": name in required,
                "description": (sub.get("description") or "")[:255],
                "default": sub.get("default"),
            })
        return out
    return []


def _openapi_type(t: Optional[str], fmt: Optional[str]) -> str:
    """Map OpenAPI primitive types to our ParamType enum."""
    if t == "integer":
        return "int"
    if t == "number":
        return "number"
    if t == "boolean":
        return "boolean"
    if t == "array":
        return "array"
    if t == "object":
        return "object"
    if t == "string":
        if fmt in ("date",):
            return "date"
        if fmt in ("date-time",):
            return "datetime"
        return "string"
    return "string"


def _slug_from_path(method: str, path: str) -> str:
    """Build a stable slug for paths that lack operationId."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_")
    return f"{method.lower()}_{cleaned}"[:128] or "anon_call"


def _dedupe_params(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in rows:
        key = (r.get("name", ""), r.get("location", "body"))
        if key not in seen:
            seen[key] = r
    return list(seen.values())


# ---------------------------------------------------------------------
# Strategy 2: Postman Collection
# ---------------------------------------------------------------------

def _try_postman(url: str) -> List[CandidateAPIDef]:
    import json

    try:
        status, _, body = _fetch(url, accept="application/json")
    except Exception:
        return []
    if status >= 400:
        return []
    try:
        col = json.loads(body.decode("utf-8", errors="replace"))
    except (ValueError, UnicodeDecodeError):
        return []

    info = col.get("info") or {}
    schema = (info.get("schema") or "").lower()
    if "postman" not in schema:
        return []

    candidates: List[CandidateAPIDef] = []
    _walk_postman_items(col.get("item") or [], candidates, doc_url=url)
    return candidates


def _walk_postman_items(items: List[Any], out: List[CandidateAPIDef], *, doc_url: str) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        sub = item.get("item")
        if isinstance(sub, list):
            _walk_postman_items(sub, out, doc_url=doc_url)
            continue
        request = item.get("request")
        if not isinstance(request, dict):
            continue

        method = (request.get("method") or "GET").upper()
        url_obj = request.get("url")
        if isinstance(url_obj, dict):
            raw = url_obj.get("raw") or ""
        else:
            raw = str(url_obj or "")
        if not raw:
            continue

        body_obj = request.get("body") or {}
        params = _postman_body_to_params(body_obj)
        if isinstance(url_obj, dict):
            params += _postman_query_to_params(url_obj.get("query") or [])

        out.append(CandidateAPIDef(
            call=str(item.get("name") or "").strip().replace(" ", "_")[:128] or "anon_call",
            method=method,
            url=raw,
            description=(item.get("description") or "")[:255],
            param_schema=params,
            source_strategy=STRATEGY_POSTMAN,
            confidence=0.9,
            documentation_url=doc_url,
            notes="From Postman Collection.",
        ))


def _postman_body_to_params(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    mode = body.get("mode")
    if mode == "raw":
        # Try to parse as JSON; if it works, surface top-level keys.
        import json
        raw = body.get("raw") or ""
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        if isinstance(parsed, dict):
            return [{
                "name": k, "type": _python_type(v), "location": "body",
                "required": False, "default": v,
            } for k, v in parsed.items()]
    elif mode == "urlencoded":
        return [{
            "name": p.get("key"), "type": "string", "location": "body",
            "required": False, "default": p.get("value"),
        } for p in (body.get("urlencoded") or []) if p.get("key")]
    return []


def _postman_query_to_params(query: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{
        "name": q.get("key"), "type": "string", "location": "query",
        "required": False, "default": q.get("value"),
    } for q in (query or []) if q.get("key")]


def _python_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


# ---------------------------------------------------------------------
# Strategy 3: HTML heuristic
# ---------------------------------------------------------------------

# URL-in-code heuristic: find ``<code>`` / ``<pre>`` blocks containing
# something that looks like an HTTP URL. Each match becomes a low-
# confidence candidate. Method defaults to GET unless a verb prefix is
# detected (``POST https://...``, ``GET /...``).
_VERB_URL_RE = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE)\s+(https?://[^\s<>\"']+|/[^\s<>\"']+)",
    re.IGNORECASE,
)
_BARE_URL_RE = re.compile(r"https?://[^\s<>\"']+")
# Strip HTML tags + entities at parse time. Lightweight; avoids
# pulling BeautifulSoup just for this fallback.
_TAG_RE = re.compile(r"<[^>]+>")


def _try_html(url: str) -> List[CandidateAPIDef]:
    try:
        status, headers, body = _fetch(url, accept="text/html, */*")
    except Exception:
        return []
    if status >= 400:
        return []

    # Skip JSON / XML payloads; only handle HTML-ish.
    ctype = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
    if "html" not in ctype and "text" not in ctype:
        return []

    text = body.decode("utf-8", errors="replace")
    # Remove tags so we operate on plain content.
    plain = _TAG_RE.sub(" ", text)

    seen: set = set()
    candidates: List[CandidateAPIDef] = []

    # Pass 1: explicit method-prefixed URLs.
    for m in _VERB_URL_RE.finditer(plain):
        method = m.group(1).upper()
        target = m.group(2).strip()
        key = (method, target)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(_html_candidate(method, target, url, confidence=0.6))

    # Pass 2: bare URLs (default to GET, lower confidence).
    for m in _BARE_URL_RE.finditer(plain):
        target = m.group(0).strip().rstrip(".,)”\"'")
        key = ("GET", target)
        if key in seen:
            continue
        # Skip non-API-looking URLs (homepages, asset hosts, docs index).
        if not _looks_like_api(target):
            continue
        seen.add(key)
        candidates.append(_html_candidate("GET", target, url, confidence=0.4))

    # Cap at 80 — operator can refine the URL if more are needed.
    return candidates[:80]


def _html_candidate(method: str, target: str, doc_url: str, *, confidence: float) -> CandidateAPIDef:
    full = target if target.startswith("http") else urljoin(doc_url, target)
    parsed = urlparse(full)
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", parsed.path).strip("_") or "root"
    return CandidateAPIDef(
        call=f"{method.lower()}_{slug}"[:128],
        method=method,
        url=full,
        description="",
        param_schema=[],
        source_strategy=STRATEGY_HTML,
        confidence=confidence,
        documentation_url=doc_url,
        notes="Inferido por scraping HTML.",
    )


def _looks_like_api(target: str) -> bool:
    """Quick filter: only bare URLs that contain ``/api/`` or ``/v1/``
    or end in ``.json`` are worth surfacing as candidates by default."""
    low = target.lower()
    return any(token in low for token in ("/api/", "/v1/", "/v2/", "/rest/", ".json"))


# ---------------------------------------------------------------------
# Strategy 4: LLM-assisted (opt-in)
# ---------------------------------------------------------------------

LLM_DISCOVERY_PROMPT = """\
You are extracting API endpoint definitions from a documentation page.

Return ONLY a JSON array (no prose). Each element MUST have these keys:
  - call (string, slug-like id)
  - method (one of GET, POST, PUT, PATCH, DELETE)
  - url (string, absolute or relative)
  - description (string, short)
  - params (array of {name, type, location: body|query|path|header, required: boolean})

Skip examples that look like marketing or non-API URLs. Cap at 50
endpoints. If the page does not describe an API, return [].

PAGE CONTENT:
"""


def _try_llm(url: str, *, llm_caller: Any) -> List[CandidateAPIDef]:
    """LLM is opt-in (caller must pass ``allow_llm=True`` and a
    ``llm_caller``). The caller is responsible for redaction and any
    secret-handling — this layer just ferries text in / JSON out."""
    import json

    try:
        status, _, body = _fetch(url, accept="text/html, */*")
    except Exception:
        return []
    if status >= 400:
        return []

    text = body.decode("utf-8", errors="replace")
    plain = _TAG_RE.sub(" ", text)
    # Hard cap on input size — cost + latency.
    if len(plain) > 100_000:
        plain = plain[:100_000]

    raw = llm_caller(LLM_DISCOVERY_PROMPT, plain)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []

    candidates: List[CandidateAPIDef] = []
    for item in parsed[:50]:
        if not isinstance(item, dict):
            continue
        method = str(item.get("method", "GET")).upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            continue
        target = item.get("url")
        if not target:
            continue
        params_raw = item.get("params") or []
        params: List[Dict[str, Any]] = []
        for p in params_raw if isinstance(params_raw, list) else []:
            if not isinstance(p, dict) or not p.get("name"):
                continue
            params.append({
                "name": p.get("name"),
                "type": p.get("type", "string"),
                "location": p.get("location", "body"),
                "required": bool(p.get("required", False)),
            })
        candidates.append(CandidateAPIDef(
            call=str(item.get("call") or "anon_call")[:128],
            method=method,
            url=str(target),
            description=str(item.get("description") or "")[:255],
            param_schema=params,
            source_strategy=STRATEGY_LLM,
            confidence=0.7,
            documentation_url=url,
            notes="Inferido por LLM (opt-in).",
        ))
    return candidates

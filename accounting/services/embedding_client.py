# accounting/services/embedding_client.py
from __future__ import annotations
from typing import List, Sequence, Optional, Dict, Any
import math
import logging
import requests
from django.conf import settings

log = logging.getLogger("recon")  # or "embeddings"

def _embed_base_url() -> str:
    """
    Prefer the Railway internal endpoint (http), otherwise fallback to EMBED_BASE_URL.
    """
    if settings.EMBED_INTERNAL_HOST:
        return f"http://{settings.EMBED_INTERNAL_HOST}:{settings.EMBED_PORT}"
    if settings.EMBED_BASE_URL:
        return settings.EMBED_BASE_URL.rstrip("/")
    # last resort: localhost (dev)
    return "http://localhost:11434"

def _embed_url() -> str:
    return _embed_base_url().rstrip("/") + settings.EMBED_PATH

def _fit_dim(vec: Sequence[float] | None, dim: int) -> Optional[List[float]]:
    if vec is None:
        return None
    if len(vec) == dim:
        return list(vec)
    if len(vec) > dim:
        return list(vec[:dim])
    return list(vec) + [0.0] * (dim - len(vec))

def _is_zero_vec(v: Sequence[float] | None) -> bool:
    if not v:
        return True
    try:
        # treat near-zero as zero to be safe
        return all(abs(float(x)) < 1e-12 for x in v)
    except Exception:
        return True

def _vec_stats(v: Sequence[float] | None) -> Dict[str, Any]:
    if not v:
        return {"len": 0, "norm": 0.0, "head": []}
    try:
        n = len(v)
        norm = math.sqrt(sum(float(x) * float(x) for x in v))
        return {"len": n, "norm": round(norm, 6), "head": [round(float(x), 6) for x in v[:8]]}
    except Exception:
        return {"len": 0, "norm": 0.0, "head": []}

def _parse_embeddings(payload: Dict[str, Any]) -> List[List[float]]:
    """
    Accepts common shapes:
      {"embeddings":[[...], ...]}
      {"data":[{"embedding":[...]}, ...]}
      {"embedding":[...]}  (single)
    """
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("embeddings"), list):
        emb = payload["embeddings"]
        if emb and isinstance(emb[0], list):
            return emb
        if emb and isinstance(emb[0], (int, float)):
            return [emb]
    data = payload.get("data")
    if isinstance(data, list):
        out = []
        for row in data:
            if isinstance(row, dict) and isinstance(row.get("embedding"), list):
                out.append(row["embedding"])
        if out:
            return out
    one = payload.get("embedding")
    if isinstance(one, list):
        return [one]
    return []

class EmbeddingClient:
    """
    Ollama-compatible embedding client (batch with 'input'; fallback to per-item 'prompt').
    """
    def __init__(
        self,
        model: str | None = None,
        timeout_s: float | None = None,
        dim: int | None = None,
        api_key: Optional[str] = None,
        num_thread: Optional[int] = None,
        keep_alive: Optional[str] = None,
        base_url: Optional[str] = None,
        path: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        connect_timeout_s: float | None = None,
    ):
        self.model = model or settings.EMBED_MODEL
        self.read_timeout = float(timeout_s or settings.EMBED_TIMEOUT_S)
        self.dim = int(dim or settings.EMBED_DIM)
        self.connect_timeout = float(connect_timeout_s or getattr(settings, "EMBED_CONNECT_TIMEOUT_S", 5.0))
        
        # endpoint
        if base_url:
            self.base_url = base_url.rstrip("/")
        else:
            self.base_url = _embed_base_url()
        self.path = path or settings.EMBED_PATH
        self.url = self.base_url + self.path

        self.num_thread = int(num_thread or settings.EMBED_NUM_THREAD)
        self.keep_alive = keep_alive or settings.EMBED_KEEP_ALIVE

        self.session = requests.Session()
        self.session.headers.update({"content-type": "application/json"})
        # optional auth (not required for internal)
        key = api_key or settings.EMBED_API_KEY
        if key:
            self.session.headers.update({
                "Authorization": f"Bearer {key}",
                "X-API-Key": key,
            })
        if extra_headers:
            self.session.headers.update(extra_headers)
        
        log.debug(
            "EmbeddingClient init url=%s model=%s dim=%s ct=%.1fs rt=%.1fs",
            self.url, self.model, self.dim, self.connect_timeout, self.read_timeout
        )
    
    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = self.session.post(self.url, json=payload, timeout=(self.connect_timeout, self.read_timeout))
        r.raise_for_status()
        return r.json()
        
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        
        clean = [(t or "").strip() or " " for t in texts]
        #log.debug("emb.embed batch n=%d model=%s url=%s", len(clean), self.model, self.url)
        
        # ---- Per-item fallback ----
        out: List[List[float]] = []
        for i, t in enumerate(clean):
            item_payload = {
                "model": self.model,
                "prompt": t,
                "options": {"num_thread": self.num_thread},
                "keep_alive": self.keep_alive,
            }
            resp = self._post(item_payload)
            vv = _parse_embeddings(resp)
            if not vv or not isinstance(vv[0], list) or _is_zero_vec(vv[0]):
                log.error("emb.item empty/zero at idx=%d text='%s' resp_keys=%s", i, t[:60], list(resp.keys()))
                raise RuntimeError(f"Embedding backend returned empty/zero vector (idx={i})")
            vec = _fit_dim(vv[0], self.dim)
            out.append(vec)
            if i == 0:
                log.debug("emb.item first stats=%s", _vec_stats(vec))
        return out

    def embed_one(self, text: str) -> List[float]:
        vs = self.embed_texts([text])
        if not vs or _is_zero_vec(vs[0]):
            raise RuntimeError("empty/zero embedding from backend")
        return vs[0]

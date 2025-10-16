# accounting/services/embedding_client.py
from __future__ import annotations
from typing import List, Sequence, Optional, Dict, Any
import requests

from django.conf import settings

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
        # could be list[list[float]] or list[float]
        if emb and isinstance(emb[0], list):
            return emb
        if emb and isinstance(emb[0], (int, float)):
            return [emb]
    data = payload.get("data")
    if isinstance(data, list):
        out = []
        for row in data:
            e = row.get("embedding") if isinstance(row, dict) else None
            if isinstance(e, list):
                out.append(e)
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
    ):
        self.model = model or settings.EMBED_MODEL
        self.timeout = float(timeout_s or settings.EMBED_TIMEOUT_S)
        self.dim = int(dim or settings.EMBED_DIM)

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

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        # Prefer true batch (Ollama supports "input": list)
        payload = {
            "model": self.model,
            "input": texts,
            "options": {"num_thread": self.num_thread},
            "keep_alive": self.keep_alive,
        }
        r = self.session.post(self.url, json=payload, timeout=self.timeout)
        r.raise_for_status()
        vecs = _parse_embeddings(r.json())
        if vecs and len(vecs) == len(texts):
            return [_fit_dim(v, self.dim) for v in vecs]

        # Fallback: per-item prompt (some backends require it)
        out: List[List[float]] = []
        for t in texts:
            rr = self.session.post(
                self.url,
                json={
                    "model": self.model,
                    "prompt": t,
                    "options": {"num_thread": self.num_thread},
                    "keep_alive": self.keep_alive,
                },
                timeout=self.timeout,
            )
            rr.raise_for_status()
            vv = _parse_embeddings(rr.json())
            out.append(_fit_dim(vv[0] if vv else [], self.dim) or [])
        return out

    def embed_one(self, text: str) -> List[float]:
        vs = self.embed_texts([text])
        if not vs or not vs[0]:
            raise RuntimeError("empty embedding from backend")
        return vs[0]

import requests
from typing import Any, Dict, List, Optional, Sequence
from django.conf import settings
from urllib.parse import urljoin, urlparse

class EmbeddingClient:
    """Calls Service A (Embeddings) /api/embeddings. Optimized for nomic-embed-text."""
    def __init__(self,
                 base_url: str = settings.EMBED_SVC_URL,
                 model: str = settings.EMBED_MODEL,
                 timeout_s: float = settings.EMBED_TIMEOUT,
                 dim: int = settings.EMBED_DIM,
                 keep_alive: str = settings.EMBED_KEEP,
                 headers: Optional[Dict[str, str]] = None):
        self.url = base_url.rstrip("/") + "/api/embeddings"
        self.model = model
        self.timeout = timeout_s
        self.dim = dim
        self.keep_alive = keep_alive
        self.sess = requests.Session()
        self.sess.headers.update({"content-type": "application/json"})
        if headers:
            self.sess.headers.update(headers)

    @staticmethod
    def _fit_dim(v: Sequence[float], dim: int) -> List[float]:
        if len(v) == dim: return list(v)
        if len(v) > dim:  return list(v[:dim])
        return list(v) + [0.0] * (dim - len(v))

    @staticmethod
    def _parse(resp: Dict[str, Any]) -> List[List[float]]:
        # accept {"embedding":[..]}, {"embeddings":[[..],..]}, {"data":[{"embedding":[..]},..]}
        if "embeddings" in resp and isinstance(resp["embeddings"], list):
            if resp["embeddings"] and isinstance(resp["embeddings"][0], list):
                return resp["embeddings"]
            if resp["embeddings"] and isinstance(resp["embeddings"][0], (int,float)):
                return [resp["embeddings"]]
        if "embedding" in resp and isinstance(resp["embedding"], list):
            return [resp["embedding"]]
        data = resp.get("data")
        if isinstance(data, list):
            out = []
            for r in data:
                e = r.get("embedding")
                if isinstance(e, list): out.append(e)
            if out: return out
        raise ValueError(f"Unexpected embedding response: {resp!r}")

    def embed_many(self, texts: List[str]) -> List[List[float]]:
        if not texts: return []
        # nomic supports batch via "input"
        r = self.sess.post(
            self.url,
            json={"model": self.model, "input": texts, "keep_alive": self.keep_alive},
            timeout=self.timeout,
        )
        r.raise_for_status()
        vecs = self._parse(r.json())
        if len(vecs) != len(texts):
            # fallback to one-by-one with "prompt"
            out = []
            for t in texts:
                rr = self.sess.post(
                    self.url,
                    json={"model": self.model, "prompt": t, "keep_alive": self.keep_alive},
                    timeout=self.timeout,
                )
                rr.raise_for_status()
                vv = self._parse(rr.json())[0]
                out.append(self._fit_dim(vv, self.dim))
            return out
        return [self._fit_dim(v, self.dim) for v in vecs]

    def embed_one(self, text: str) -> List[float]:
        return self.embed_many([text])[0]


class LlmClient:
    """Local LLM on Service B (Ollama /api/generate)."""
    def __init__(self, base_url, path="/api/generate", model="llama3.2:3b-instruct:q4_K_M",
                 timeout=20, headers=None):
        self.base_url = self._normalize_base(base_url)
        self.url = urljoin(self.base_url + "/", (path or "/api/generate").lstrip("/"))
        self.model = model
        self.timeout = timeout

        self.sess = requests.Session()
        self.sess.headers.update({"content-type": "application/json"})
        if headers:
            self.sess.headers.update(headers)

    @staticmethod
    def _normalize_base(u: str) -> str:
        if not u:
            raise ValueError("LLM base URL is not configured")
        # Auto-add scheme when missing
        if "://" not in u:
            u = "http://" + u
        return u.rstrip("/")

    def generate(self, prompt: str, temperature=0.2, num_predict=400, keep_alive="30m"):
        payload = {
            "model": self.model,
            "prompt": prompt,
            "options": {"temperature": temperature, "num_predict": num_predict},
            "keep_alive": keep_alive,
        }
        r = self.sess.post(self.url, json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()
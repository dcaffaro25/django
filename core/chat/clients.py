import requests
from typing import Any, Dict, List, Optional, Sequence
from django.conf import settings

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
    def __init__(self,
                 base_url: str = settings.LLM_BASE_URL,
                 model: str = settings.LLM_MODEL,
                 timeout_s: float = settings.LLM_TIMEOUT,
                 keep_alive: str = settings.EMBED_KEEP):
        self.url = base_url.rstrip("/") + "/api/generate"
        self.model = model
        self.timeout = timeout_s
        self.keep_alive = keep_alive
        self.sess = requests.Session()
        self.sess.headers.update({"content-type": "application/json"})

    def generate(self, prompt: str, **opts) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": opts.get("temperature", 0.2),
                "num_predict": opts.get("num_predict", 400),
            },
            "stream": False,
        }
        r = self.sess.post(self.url, json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        # Ollama returns either {'response': '...'} or chunks when stream=true
        return data.get("response") or data.get("text") or ""

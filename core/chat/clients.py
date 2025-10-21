import requests
from typing import Any, Dict, List, Optional, Sequence
from django.conf import settings
from urllib.parse import urljoin, urlparse
import json
import logging
import uuid
import time

log = logging.getLogger("chat.llm")

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
    """
    Thin client for an Ollama-compatible /api/generate.
    - Streams JSONL and stitches tokens.
    - Emits timing metrics: connect_ms, ttfb_ms, stream_ms, total_ms
    - Logs key steps with a request_id so you can grep logs across services.
    """

    def __init__(
        self,
        base_url: str,
        path: str = "/api/generate",
        model: str = "llama3.2:3b-instruct-q4_K_M",
        timeout: float = 180.0,
        headers: Optional[Dict[str, str]] = None,
    ):
        if not base_url:
            raise ValueError("LLM base URL is not configured")
        if "://" not in base_url:
            base_url = "http://" + base_url  # auto-scheme for railway.internal
        self.url = urljoin(base_url.rstrip("/") + "/", (path or "/api/generate").lstrip("/"))
        self.model = model
        self.timeout = float(timeout)

        self.sess = requests.Session()
        self.sess.headers.update({"content-type": "application/json"})
        if headers:
            self.sess.headers.update(headers)

        log.debug("LlmClient init url=%s model=%s timeout_s=%.1f", self.url, self.model, self.timeout)

    def generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        num_predict: int = 300,
        keep_alive: str = "45m",
        request_id: Optional[str] = None,
        debug: bool = False,
    ) -> Dict[str, Any]:
        rid = request_id or str(uuid.uuid4())
        payload = {
            "model": self.model,
            "prompt": prompt,
            "options": {"temperature": temperature, "num_predict": num_predict},
            "keep_alive": keep_alive,
            "stream": True,
        }

        # Split connect/read timeouts: (connect, read)
        connect_timeout = 5.0
        read_timeout = max(self.timeout, 5.0)

        log.info(
            "[%s] LLM call begin url=%s model=%s temp=%.2f num_predict=%s",
            rid, self.url, self.model, temperature, num_predict
        )

        t0 = time.perf_counter()
        first_headers = None
        first_chunk_at = None
        tok_count = 0
        bytes_in = 0
        parts: List[str] = []
        done_reason = None
        backend_metrics: Dict[str, Any] = {}

        try:
            with self.sess.post(self.url, json=payload, timeout=(connect_timeout, read_timeout), stream=True) as r:
                r.raise_for_status()
                first_headers = time.perf_counter()
                log.debug("[%s] headers ok status=%s", rid, r.status_code)

                for raw in r.iter_lines(decode_unicode=True):
                    if raw is None or raw == "":
                        continue
                    if first_chunk_at is None:
                        first_chunk_at = time.perf_counter()
                        log.debug("[%s] first chunk arrived", rid)

                    bytes_in += len(raw)
                    try:
                        obj = json.loads(raw)
                    except Exception:
                        # If a noisy line occurs, skip but keep counting
                        log.warning("[%s] non-JSON stream line skipped: %r", rid, raw[:120])
                        continue

                    if "response" in obj:
                        tok = obj["response"]
                        parts.append(tok)
                        tok_count += 1

                    # Ollama returns metrics on the 'done' record
                    if obj.get("done"):
                        done_reason = obj.get("done_reason")
                        for k in ("load_duration", "prompt_eval_duration", "eval_duration", "total_duration",
                                  "eval_count", "prompt_eval_count"):
                            if k in obj:
                                backend_metrics[k] = obj[k]
                        break

                    if obj.get("error"):
                        raise RuntimeError(obj["error"])

        except Exception as e:
            t_end = time.perf_counter()
            connect_ms = round((first_headers - t0) * 1000, 1) if first_headers else None
            ttfb_ms = round((first_chunk_at - first_headers) * 1000, 1) if first_headers and first_chunk_at else None
            total_ms = round((t_end - t0) * 1000, 1)
            log.error(
                "[%s] LLM error: %s | url=%s model=%s connect_ms=%s ttfb_ms=%s total_ms=%s bytes=%s toks=%s",
                rid, e, self.url, self.model, connect_ms, ttfb_ms, total_ms, bytes_in, tok_count,
                exc_info=True,
            )
            raise

        t_end = time.perf_counter()
        connect_ms = round((first_headers - t0) * 1000, 1) if first_headers else None
        ttfb_ms = round((first_chunk_at - first_headers) * 1000, 1) if first_headers and first_chunk_at else None
        stream_ms = round((t_end - (first_chunk_at or first_headers or t0)) * 1000, 1)
        total_ms = round((t_end - t0) * 1000, 1)

        log.info(
            "[%s] LLM done ok reason=%s toks=%s bytes=%s connect_ms=%s ttfb_ms=%s stream_ms=%s total_ms=%s",
            rid, done_reason, tok_count, bytes_in, connect_ms, ttfb_ms, stream_ms, total_ms
        )

        out = {"response": "".join(parts), "done": True, "done_reason": done_reason}
        if debug:
            out["metrics"] = {
                "connect_ms": connect_ms,
                "ttfb_ms": ttfb_ms,
                "stream_ms": stream_ms,
                "total_ms": total_ms,
                "bytes_in": bytes_in,
                "tokens": tok_count,
                "backend": backend_metrics,
                "url": self.url,
                "model": self.model,
            }
        return out
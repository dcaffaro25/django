import json, socket, time, logging, uuid, requests
from typing import Any, Dict, List, Optional, Sequence
from django.conf import settings
from urllib.parse import urljoin, urlparse




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


def _fast_probe(base_url: str, timeout_s: float = 3.0) -> dict:
    out = {"ok": False, "url": base_url}
    if "://" not in base_url:
        base_url = "http://" + base_url
    base_url = base_url.rstrip("/")
    pu = urlparse(base_url)
    host = pu.hostname
    port = pu.port or (443 if pu.scheme == "https" else 80)

    # TCP check
    try:
        t0 = time.perf_counter()
        with socket.create_connection((host, port), timeout=timeout_s):
            out["tcp_ms"] = int((time.perf_counter() - t0) * 1000)
            out["tcp_ok"] = True
    except Exception as e:
        out["tcp_ok"] = False
        out["tcp_err"] = str(e)
        return out

    # /api/version
    try:
        t1 = time.perf_counter()
        r = requests.get(f"{base_url}/api/version", timeout=timeout_s)
        out["ver_ms"] = int((time.perf_counter() - t1) * 1000)
        out["http_code"] = r.status_code
        out["ok"] = 200 <= r.status_code < 300
        out["body"] = r.text[:200]
    except Exception as e:
        out["http_err"] = str(e)
    return out


def _truncate(s: str, n: int = 800) -> str:
    if not isinstance(s, str):
        return ""
    return s if len(s) <= n else s[:n] + f"... ({len(s)} chars)"

class LlmClient:
    """Ollama /api/generate with detailed debug logging; works with stream or non-stream."""
    def __init__(
        self,
        base_url: str,
        path: str = "/api/generate",
        model: str | None = None,
        timeout: float = 60.0,
        keep_alive: str | None = None,
        default_options: dict | None = None,
        headers: dict | None = None,
    ):
        # Normalize base URL
        if "://" not in base_url:
            base_url = "http://" + base_url
        self.base_url = base_url.rstrip("/")
        self.url = urljoin(self.base_url + "/", (path or "/api/generate").lstrip("/"))

        self.model = model or getattr(settings, "LLM_MODEL", "llama3.2:3b-instruct-q4_K_M")
        self.timeout = float(timeout or getattr(settings, "LLM_TIMEOUT_S", 60.0))
        self.keep_alive = keep_alive or getattr(settings, "LLM_KEEP_ALIVE", "30m")
        self.default_options = default_options or {
            "temperature": 0.2,
            "num_predict": 256,
            # "num_thread": int(getattr(settings, "LLM_NUM_THREAD", 8)),  # optional
        }

        self.sess = requests.Session()
        self.sess.headers.update({"content-type": "application/json"})
        if headers:
            self.sess.headers.update(headers)

        log.debug(
            "LlmClient init base=%s url=%s model=%s timeout=%.1f keep=%s",
            self.base_url, self.url, self.model, self.timeout, self.keep_alive
        )

    def _merge_options(self, caller_opts: dict | None) -> dict:
        merged = dict(self.default_options)
        if caller_opts:
            merged.update({k: v for k, v in caller_opts.items() if v is not None})
        return merged

    def generate(
        self,
        prompt: str,
        stream: bool | None = None,
        keep_alive: str | None = None,
        options: dict | None = None,
        connect_timeout: float = 5.0,
        read_timeout: float | None = None,
    ):
        req_id = uuid.uuid4().hex[:8]

        # Effective params (non-stream by default: good for Retool)
        effective_model = self.model
        effective_stream = bool(stream) if stream is not None else False
        effective_keep = keep_alive or self.keep_alive
        effective_options = self._merge_options(options)
        read_timeout = float(read_timeout or self.timeout)

        payload = {
            "model": effective_model,
            "prompt": prompt or "",
            "options": effective_options,
            "keep_alive": effective_keep,
            "stream": effective_stream,
        }

        if log.isEnabledFor(logging.INFO):
            log.info(
                "[llm %s] POST %s model=%s stream=%s keep=%s opts=%s prompt(%.0f)='%s'",
                req_id, self.url, effective_model, effective_stream, effective_keep,
                json.dumps({k: v for k, v in effective_options.items()}, separators=(",", ":")),
                float(len(payload["prompt"])), _truncate(payload["prompt"], 300)
            )

        t0 = time.perf_counter()

        # If you **don’t** want server streaming, don’t ask requests to stream.
        if not effective_stream:
            r = self.sess.post(self.url, json=payload, timeout=(connect_timeout, read_timeout))
            r.raise_for_status()
            data = r.json()
            total_ms = (time.perf_counter() - t0) * 1000.0
            resp = data.get("response", "")
            log.info("[llm %s] 200 OK non-stream in %.1f ms, out_chars=%d", req_id, total_ms, len(resp))
            return {
                "response": resp,
                "done": bool(data.get("done", True)),
                "raw": data,
                "ms": total_ms,
            }

        # Streaming branch (NDJSON). Retool won’t display partials, but we support it.
        text_parts, bytes_seen = [], 0
        with self.sess.post(self.url, json=payload, timeout=(connect_timeout, read_timeout), stream=True) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                bytes_seen += len(line)
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if "response" in obj:
                    text_parts.append(obj["response"])
                if obj.get("error"):
                    log.error("[llm %s] stream error: %s", req_id, obj["error"])
                    raise RuntimeError(obj["error"])
                if obj.get("done"):
                    break

        total_ms = (time.perf_counter() - t0) * 1000.0
        resp = "".join(text_parts)
        log.info("[llm %s] 200 OK stream in %.1f ms, bytes=%d, out_chars=%d",
                 req_id, total_ms, bytes_seen, len(resp))
        return {"response": resp, "done": True, "ms": total_ms}
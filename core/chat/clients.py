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


class LlmClient:
    """Ollama /api/generate with detailed debug logging."""
    def __init__(self, base_url, path="/api/generate", model="llama3.2:3b-instruct-q4_K_M",
                 timeout=300, headers=None):
        raw_base = base_url
        if "://" not in base_url:
            base_url = "http://" + base_url
        self.base_url = base_url.rstrip("/")
        self.url = urljoin(self.base_url + "/", (path or "/api/generate").lstrip("/"))
        self.model = model
        self.timeout = timeout

        self.sess = requests.Session()
        self.sess.headers.update({"content-type": "application/json"})
        if headers:
            self.sess.headers.update(headers)

        log.debug("LlmClient init raw_base=%s base_url=%s url=%s model=%s timeout=%s",
                  raw_base, self.base_url, self.url, self.model, self.timeout)

    def generate(self, prompt: str, temperature=0.2, num_predict=300, keep_alive="45m"):
        req_id = uuid.uuid4().hex[:8]
    
        probe = _fast_probe(self.base_url, timeout_s=3.0)
        log.info("[llm %s] probe=%s", req_id, probe)
        if not probe.get("ok"):
            raise RuntimeError(f"LLM upstream not ready: {probe}")
    
        # ---- WARMUP (best-effort) ----
        warm_payload = {
            "model": self.model,
            "prompt": "ping",
            "options": {"temperature": 0.0, "num_predict": 1},
            "keep_alive": keep_alive,
            "stream": False,
        }
        tw0 = time.perf_counter()
        try:
            # give cold-load real time to finish (connect 5s, read 120s)
            r0 = self.sess.post(self.url, json=warm_payload, timeout=(5, 120))
            r0.raise_for_status()
            log.info("[llm %s] warmup ok in %.1f ms", req_id, (time.perf_counter()-tw0)*1000)
        except Exception as e:
            # DO NOT abort; just log and proceed to main call
            log.warning("[llm %s] warmup skipped (%s) after %.1f ms",
                        req_id, str(e), (time.perf_counter()-tw0)*1000)
    
        # ---- REAL STREAMED CALL ----
        payload = {
            "model": self.model,
            "prompt": prompt,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
                # threads can help on CPU; wire via env if you like
                # "num_thread": int(os.getenv("LLM_NUM_THREAD", "8")),
                # keep other options minimal for reliability
            },
            "keep_alive": keep_alive,
            "stream": True,
        }
        connect_timeout, read_timeout = 5, self.timeout  # e.g. 300s
        log.info("[llm %s] POST %s model=%s prompt_chars=%d temp=%.2f num_predict=%d",
                 req_id, self.url, self.model, len(prompt), temperature, num_predict)
    
        text_parts, bytes_seen = [], 0
        t0 = time.perf_counter()
        with self.sess.post(self.url, json=payload, timeout=(connect_timeout, read_timeout), stream=True) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                bytes_seen += len(line)
                if bytes_seen and bytes_seen % 8192 < 100:
                    log.debug("[llm %s] stream progress bytes=%d", req_id, bytes_seen)
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
    
        total_ms = (time.perf_counter() - t0) * 1000
        resp = "".join(text_parts)
        log.info("[llm %s] done in %.1f ms, bytes=%d, out_chars=%d",
                 req_id, total_ms, bytes_seen, len(resp))
        return {"response": resp, "done": True}
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from .serializers import AskSerializer
from .clients import EmbeddingClient, LlmClient
from .retrieval import embed_query, topk_union, build_context
import time, logging, uuid

log = logging.getLogger("chat.view")

SYSTEM_PROMPT = """You are a financial analyst assistant.
- Read the provided context (transactions, bank transactions, accounts).
- Answer the user's question concisely.
- Show short bullet summaries if the user asks for "summaries" or "trends".
- If the answer depends on uncertain context, say what else would help.
Return only the answer; do not include the context back.
"""

class ChatHealthView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        import time
        llm = LlmClient(
            base_url=settings.LLM_BASE_URL,
            path=settings.LLM_GENERATE_PATH,
            model=settings.LLM_MODEL,
            timeout=30,
        )
        t0 = time.perf_counter()
        try:
            out = llm.generate("ping", num_predict=8, temperature=0.0)
            ms = int((time.perf_counter() - t0) * 1000)
            return Response({"ok": True, "latency_ms": ms, "url": llm.url}, 200)
        except Exception as e:
            ms = int((time.perf_counter() - t0) * 1000)
            return Response({"ok": False, "latency_ms": ms, "error": str(e), "url": llm.url}, 503)

def _want_debug(request) -> bool:
    """Enable response-side debug via ?debug=1 or header X-Debug: 1 (and always log)."""
    qp = request.query_params.get("debug")
    hd = request.headers.get("X-Debug")
    if str(qp).lower() in ("1", "true", "yes"):  # noqa
        return True
    if str(hd).lower() in ("1", "true", "yes"):
        return True
    return bool(getattr(settings, "DEBUG", False))  # optional

vlog = logging.getLogger("chat.view")

class ChatAskView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        req_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:8]
        q = request.data.get("query") or ""
        temperature = float(request.data.get("temperature", 0.2))
        num_predict = int(request.data.get("num_predict", 256))

        llm = LlmClient(
            base_url=getattr(settings, "LLM_BASE_URL"),
            path=getattr(settings, "LLM_GENERATE_PATH", "/api/generate"),
            model=getattr(settings, "LLM_MODEL", "llama3.2:3b-instruct-q4_K_M"),
            timeout=getattr(settings, "LLM_TIMEOUT_S", 300),
        )

        vlog.info("[chat %s] ask qchars=%d temp=%.2f num_predict=%d url=%s model=%s",
                  req_id, len(q), temperature, num_predict, llm.url, llm.model)

        t0 = time.perf_counter()
        try:
            out = llm.generate(q, temperature=temperature, num_predict=num_predict)
            dur_ms = (time.perf_counter() - t0) * 1000
            preview = (out["response"] or "")[:160]
            vlog.info("[chat %s] ok in %.1f ms preview=%r", req_id, dur_ms, preview)
            return Response({"success": True, "response": out["response"], "ms": int(dur_ms)}, status=200)
        except Exception as e:
            dur_ms = (time.perf_counter() - t0) * 1000
            vlog.exception("[chat %s] ERROR in %.1f ms url=%s model=%s", req_id, dur_ms, llm.url, llm.model)
            return Response(
                {
                    "success": False,
                    "error": str(e),
                    "resolved_url": llm.url,
                    "base_url": llm.base_url,
                    "model": llm.model,
                    "ms": int(dur_ms),
                    "request_id": req_id,
                },
                status=502,
            )
        
class ChatDiagView(APIView):
    permission_classes = []  # temporarily open; restrict later

    def get(self, request):
        from .clients import _fast_probe, LlmClient
        llm = LlmClient(
            base_url=getattr(settings, "LLM_BASE_URL"),
            path=getattr(settings, "LLM_GENERATE_PATH", "/api/generate"),
            model=getattr(settings, "LLM_MODEL", "llama3.2:3b-instruct-q4_K_M"),
            timeout=10,
        )
        probe = _fast_probe(llm.base_url, timeout_s=3.0)
        return Response({
            "LLM_BASE_URL": getattr(settings, "LLM_BASE_URL"),
            "resolved_base": llm.base_url,
            "resolved_url": llm.url,
            "model": llm.model,
            "probe": probe,
        })
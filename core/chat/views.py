from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from .serializers import AskSerializer
from .clients import EmbeddingClient, LlmClient
from .retrieval import embed_query, topk_union, build_context
import logging
import time

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

class ChatAskView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        t0 = time.perf_counter()
        q = (request.data.get("query") or "").strip()
        temperature = float(request.data.get("temperature", 0.2))
        num_predict = int(request.data.get("num_predict", 256))
        debug_resp = _want_debug(request)

        # Log the incoming request (safe fields only)
        log.info(
            "chat.ask begin user=%s qlen=%s temp=%.2f num_predict=%s",
            getattr(request.user, "id", None), len(q), temperature, num_predict
        )
        log.debug(
            "LLM config base=%s path=%s model=%s timeout_s=%s",
            getattr(settings, "LLM_BASE_URL", None),
            getattr(settings, "LLM_GENERATE_PATH", "/api/generate"),
            getattr(settings, "LLM_MODEL", None),
            getattr(settings, "LLM_TIMEOUT_S", None),
        )

        llm = LlmClient(
            base_url=getattr(settings, "LLM_BASE_URL"),
            path=getattr(settings, "LLM_GENERATE_PATH", "/api/generate"),
            model=getattr(settings, "LLM_MODEL", "llama3.2:3b-instruct-q4_K_M"),
            timeout=getattr(settings, "LLM_TIMEOUT_S", 180),
        )

        try:
            out = llm.generate(
                q,
                temperature=temperature,
                num_predict=num_predict,
                request_id=request.headers.get("X-Request-Id"),
                debug=debug_resp,
            )
            t1 = time.perf_counter()
            log.info("chat.ask ok dur_ms=%s", round((t1 - t0) * 1000, 1))

            body = {"success": True, "response": out.get("response", "")}
            if debug_resp:
                body["debug"] = out.get("metrics", {})
            return Response(body, status=status.HTTP_200_OK)

        except Exception as e:
            t1 = time.perf_counter()
            log.exception("chat.ask error dur_ms=%s", round((t1 - t0) * 1000, 1))
            return Response(
                {
                    "success": False,
                    "error": str(e),
                    "resolved_url": getattr(llm, "url", None),
                    "model": getattr(llm, "model", None),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

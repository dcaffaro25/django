from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from .serializers import AskSerializer
from .clients import EmbeddingClient, LlmClient
from .retrieval import embed_query, topk_union, build_context

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

class ChatAskView(APIView):
    permission_classes = [IsAdminUser]
    def post(self, request):
        q = request.data.get("query") or ""
        temperature = float(request.data.get("temperature", 0.2))
        num_predict = int(request.data.get("num_predict", 256))  # smaller default

        llm = LlmClient(
            base_url=getattr(settings, "LLM_BASE_URL"),
            path=getattr(settings, "LLM_GENERATE_PATH", "/api/generate"),
            model=getattr(settings, "LLM_MODEL", "llama3.2:3b-instruct-q4_K_M"),
            timeout=getattr(settings, "LLM_TIMEOUT_S", 180),
        )
        try:
            out = llm.generate(q, temperature=temperature, num_predict=num_predict)
            return Response({"success": True, "response": out["response"]}, status=200)
        except Exception as e:
            return Response(
                {"success": False, "error": str(e), "resolved_url": llm.url},
                status=502,
            )

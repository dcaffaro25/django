from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from .serializers import AskSerializer
from .clients import EmbeddingClient, LlmClient
from .retrieval import embed_query, topk_union, build_context, should_use_rag, retrieve_context, json_safe
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
    """
    POST /api/chat/ask/
    Body (any field optional; present fields override defaults):
    {
      "model": "llama3.2:1b-instruct-q4_K_M",
      "prompt": "Explain like I'm five: what is 1+1?",
      "stream": false,
      "keep_alive": "30m",
      "options": {
        "num_predict": 32,
        "temperature": 0.1,
        "top_p": 0.9,
        "num_thread": 8
      },
      "mode": "auto" | "rag" | "no_rag"
    }
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        body = request.data or {}

        # Inputs / overrides
        prompt     = body.get("prompt", "") or ""
        model      = body.get("model") or getattr(settings, "LLM_MODEL", "llama3.2:1b-instruct-q4_K_M")
        stream     = body.get("stream")  # True/False/None
        keep_alive = body.get("keep_alive") or getattr(settings, "LLM_KEEP_ALIVE", "30m")
        options    = body.get("options") or {}
        mode       = (body.get("mode") or "auto").lower()  # auto|rag|no_rag

        # Tenant/company (adjust to however your middleware exposes it)
        company = getattr(request, "company", None)  # or request.tenant.company, etc.

        # Clients
        emb = EmbeddingClient(
            base_url=getattr(settings, "EMBED_SVC_URL", "http://embedding-service.railway.internal"),
            model=getattr(settings, "EMBED_MODEL", "nomic-embed-text"),
            timeout_s=float(getattr(settings, "EMBED_TIMEOUT", 30)),
            dim=int(getattr(settings, "EMBED_DIM", 768)),
            keep_alive=getattr(settings, "EMBED_KEEP", "45m"),
        )
        llm = LlmClient(
            base_url=getattr(settings, "LLM_BASE_URL", "http://chat-service.railway.internal:11434"),
            path=getattr(settings, "LLM_GENERATE_PATH", "/api/generate"),
            model=model,
            timeout=float(getattr(settings, "LLM_TIMEOUT_S", 120.0)),
        )

        # Route: decide whether to retrieve
        use_rag = (mode == "rag") or (mode == "auto" and should_use_rag(prompt))
        log.info("[chat] mode=%s use_rag=%s model=%s stream=%s keep=%s opts=%s prompt_len=%d",
                 mode, use_rag, model, stream, keep_alive, options, len(prompt))

        # Build final prompt
        final_prompt = prompt
        citations = []
        if use_rag:
            try:
                ctx, citations = retrieve_context(prompt, emb=emb, company=company, k_each=8)
                final_prompt = (
                    f"{SYSTEM_PROMPT}\n\n"
                    f"# Context (internal knowledge)\n{ctx}\n\n"
                    f"# User question\n{prompt}\n\n"
                    f"# Your answer\n"
                )
            except Exception as e:
                # Fail open: continue without context
                log.exception("[chat] RAG failed; falling back to no_rag: %s", e)
                use_rag = False
                final_prompt = prompt

        t0 = time.perf_counter()
        try:
            result = llm.generate(
                prompt=final_prompt,
                stream=stream,
                keep_alive=keep_alive,
                options=options,
            )
            ms = int((time.perf_counter() - t0) * 1000)
            
            payload = {
                "success": True,
                "model": model,
                "mode": mode,
                "used_rag": use_rag,
                "citations": citations,
                "response": result.get("response", ""),
                "latency_ms": ms,
                "raw": result.get("raw"),  # useful for debugging non-stream
            }
            
            return Response(json_safe(payload),
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            log.exception("[chat] LLM error")
            payload = {
                    "success": False,
                    "error": str(e),
                    "base_url": llm.base_url,
                    "url": llm.url,
                    "model": model,
                    "used_rag": use_rag,
                }
            return Response(json_safe(payload),
                status=status.HTTP_502_BAD_GATEWAY,
            )

class ChatAskView_NoContext(APIView):
    """
    POST /api/chat/ask/
    Body (any field optional; present fields override defaults):
    {
      "model": "llama3.2:1b-instruct-q4_K_M",
      "prompt": "Explain like I'm five: what is 1+1?",
      "stream": false,
      "keep_alive": "30m",
      "options": {
        "num_predict": 32,
        "temperature": 0.1,
        "top_p": 0.9,
        "num_thread": 8
      }
    }
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        body = request.data or {}

        prompt      = body.get("prompt", "") or ""
        model       = body.get("model") or getattr(settings, "LLM_MODEL", "llama3.2:1b-instruct-q4_K_M")
        stream      = body.get("stream")  # may be True/False/None
        keep_alive  = body.get("keep_alive") or getattr(settings, "LLM_KEEP_ALIVE", "30m")
        options     = body.get("options") or {}

        llm = LlmClient(
            base_url="http://chat-service.railway.internal:11434",#getattr(settings, "LLM_BASE_URL", "http://chat-service.railway.internal:11434"),
            path=getattr(settings, "LLM_GENERATE_PATH", "/api/generate"),
            model=model,
            timeout=float(getattr(settings, "LLM_TIMEOUT_S", 120.0)),
        )

        log.info(
            "[chat] ask model=%s stream=%s keep=%s opts=%s prompt_len=%d",
            model, stream, keep_alive, options, len(prompt)
        )

        try:
            result = llm.generate(
                prompt=prompt,
                stream=stream,
                keep_alive=keep_alive,
                options=options,
            )
            # Retool expects a single JSON response (no SSE), so we return the final payload
            return Response(
                {"success": True, "model": model, **result},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            log.exception("[chat] LLM error")
            return Response(
                {
                    "success": False,
                    "error": str(e),
                    "base_url": llm.base_url,
                    "url": llm.url,
                    "model": model,
                },
                status=status.HTTP_502_BAD_GATEWAY,
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
            #enable_probe=False,     # <- set from env if you like
            #enable_warmup=False,    # <- set from env if you like
        )
        probe = _fast_probe(llm.base_url, timeout_s=3.0)
        return Response({
            "LLM_BASE_URL": getattr(settings, "LLM_BASE_URL"),
            "resolved_base": llm.base_url,
            "resolved_url": llm.url,
            "model": llm.model,
            "probe": probe,
        })
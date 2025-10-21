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

class ChatAskView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        ser = AskSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        q = ser.validated_data["query"]
        k_each = ser.validated_data.get("k_each", 8)
        temperature = ser.validated_data.get("temperature", 0.2)
        num_predict = ser.validated_data.get("num_predict", 400)

        emb = EmbeddingClient()
        llm = LlmClient()

        # 1) Embed query via Service A
        qvec = embed_query(q, emb)

        # 2) Vector search in our DB
        hits = topk_union(qvec, k_each=k_each)
        context, citations = build_context(hits)

        # 3) Compose prompt for local LLM
        prompt = f"{SYSTEM_PROMPT}\n\nContext:\n{context}\n\nUser: {q}\nAssistant:"
        answer = llm.generate(prompt, temperature=temperature, num_predict=num_predict)

        return Response({
            "answer": answer.strip(),
            "citations": citations,
            "retrieval": {k: len(v) for k, v in hits.items()},
            "model": settings.LLM_MODEL,
        }, status=status.HTTP_200_OK)

from typing import List, Dict, Any, Tuple
from django.db.models import F
from pgvector.django import CosineDistance
from accounting.models import Transaction, BankTransaction, Account
from .clients import EmbeddingClient

def embed_query(query: str, emb: EmbeddingClient) -> List[float]:
    return emb.embed_one(query)

def search_transactions(qvec: List[float], k: int = 10):
    return (
        Transaction.objects
        .filter(description_embedding__isnull=False)
        .annotate(score=CosineDistance("description_embedding", qvec))
        .order_by("score")[:k]
        .values("id", "description", "amount", "date", "score")
    )

def search_bank_transactions(qvec: List[float], k: int = 10):
    return (
        BankTransaction.objects
        .filter(description_embedding__isnull=False)
        .annotate(score=CosineDistance("description_embedding", qvec))
        .order_by("score")[:k]
        .values("id", "description", "amount", "date", "score")
    )

def search_accounts(qvec: List[float], k: int = 10):
    return (
        Account.objects
        .filter(account_description_embedding__isnull=False)
        .annotate(score=CosineDistance("account_description_embedding", qvec))
        .order_by("score")[:k]
        .values("id", "name", "description", "score")
    )

def topk_union(qvec: List[float], k_each: int = 8) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "transactions": list(search_transactions(qvec, k_each)),
        "bank_transactions": list(search_bank_transactions(qvec, k_each)),
        "accounts": list(search_accounts(qvec, k_each)),
    }

def build_context(hits: Dict[str, List[Dict[str, Any]]], max_chars=6000) -> Tuple[str, List[Dict[str, Any]]]:
    """Flatten hits into a compact context block for the LLM + return citations."""
    lines = []
    cites = []
    for bucket, rows in hits.items():
        for r in rows:
            if bucket == "transactions":
                lines.append(f"[TX#{r['id']} score={r['score']:.3f}] {r['date']}  ${r['amount']}  {r['description']}")
                cites.append({"type": "transaction", "id": r["id"], "score": float(r["score"])})
            elif bucket == "bank_transactions":
                lines.append(f"[BKT#{r['id']} score={r['score']:.3f}] {r['date']}  ${r['amount']}  {r['description']}")
                cites.append({"type": "bank_transaction", "id": r["id"], "score": float(r["score"])})
            else:
                lines.append(f"[ACC#{r['id']} score={r['score']:.3f}] {r['name']}  {r.get('description','')}")
                cites.append({"type": "account", "id": r["id"], "score": float(r["score"])})
    ctx = "\n".join(lines)
    if len(ctx) > max_chars:
        ctx = ctx[:max_chars] + "\n..."
    return ctx, cites

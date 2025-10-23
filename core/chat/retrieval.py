import re
import time
import logging
from typing import List, Dict, Any, Tuple, Optional
from django.db.models import F, Q
from pgvector.django import CosineDistance
from accounting.models import Transaction, BankTransaction, Account
from .clients import EmbeddingClient
import math

log = logging.getLogger("chat.rag")

RAG_KEYWORDS = [
    "transaction", "transactions", "bank", "account", "accounts", "vendor", "customer",
    "invoice", "reconcile", "reconciliation", "match", "matching",
    "spend", "expense", "revenue", "income", "trend", "summary", "summaries",
    "total", "sum", "avg", "average", "median", "month", "quarter", "year",
]

def json_safe(obj):
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    return obj

def _safe_score(v):
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return None


def should_use_rag(query: str) -> bool:
    q = (query or "").lower()
    if len(q) < 6:
        return False
    if any(k in q for k in RAG_KEYWORDS):
        return True
    # dates / money hints
    if re.search(r"\b20\d{2}\b|\b\d{4}-\d{2}-\d{2}\b|\$\s?\d", q):
        return True
    return False

def _nz(s: Optional[str]) -> str:
    return " ".join((s or "").split()).strip()

def embed_query(query: str, emb: EmbeddingClient) -> List[float]:
    return emb.embed_one(query)

def search_transactions(qvec, k=10):
    return (
        Transaction.objects
        .filter(description_embedding__isnull=False)
        .annotate(score=CosineDistance("description_embedding", qvec))
        .order_by("score")[:k]
        .values("id", "description", "amount", "date", "score")
    )

def search_bank_transactions(qvec, k=10):
    return (
        BankTransaction.objects
        .filter(description_embedding__isnull=False)
        .annotate(score=CosineDistance("description_embedding", qvec))
        .order_by("score")[:k]
        .values("id", "description", "amount", "date", "score")
    )

def search_accounts(qvec, k=10):
    return (
        Account.objects
        .filter(account_description_embedding__isnull=False)
        .annotate(score=CosineDistance("account_description_embedding", qvec))
        .order_by("score")[:k]
        .values("id", "name", "description", "score")
    )

def topk_union(qvec: List[float], company=None, k_each: int = 8) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "transactions":      list(search_transactions(qvec, company=company, k=k_each)),
        "bank_transactions": list(search_bank_transactions(qvec, company=company, k=k_each)),
        "accounts":          list(search_accounts(qvec, company=company, k=k_each)),
    }

def build_context(hits: Dict[str, List[Dict[str, Any]]], max_chars=6000):
    lines, cites = [], []
    for bucket, rows in hits.items():
        for r in rows:
            s = _safe_score(r.get("score"))
            if s is None:
                continue  # drop rows with NaN/Inf
            if bucket == "transactions":
                lines.append(f"[TX#{r['id']} score={s:.3f}] {r['date']}  ${r['amount']}  {r['description']}")
                cites.append({"type": "transaction", "id": r["id"], "score": s})
            elif bucket == "bank_transactions":
                lines.append(f"[BKT#{r['id']} score={s:.3f}] {r['date']}  ${r['amount']}  {r['description']}")
                cites.append({"type": "bank_transaction", "id": r["id"], "score": s})
            else:
                lines.append(f"[ACC#{r['id']} score={s:.3f}] {r['name']}  {r.get('description','')}")
                cites.append({"type": "account", "id": r["id"], "score": s})
    ctx = "\n".join(lines)
    if len(ctx) > max_chars:
        ctx = ctx[:max_chars] + "\n..."
    return ctx, cites

def retrieve_context(query: str, emb: EmbeddingClient, company=None, k_each=8):
    t0 = time.perf_counter()
    qvec = emb.embed_one(query)
    hits = topk_union(qvec, company=company, k_each=k_each)
    ctx, cites = build_context(hits)
    ms = int((time.perf_counter() - t0) * 1000)
    log.info("RAG retrieve ctx_len=%d cites=%d in %d ms", len(ctx), len(cites), ms)
    return ctx, cites

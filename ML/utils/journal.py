import io
import joblib
import pandas as pd
from typing import Any, Dict, List

from ML.models import MLModel

try:
    from accounting.models import Account
except Exception:
    Account = None  # type: ignore

def _transaction_to_dict(tx: Any, fields: List[str]) -> Dict[str, Any]:
    return {f: tx.get(f) if isinstance(tx, dict) else getattr(tx, f, None) for f in fields}

def suggest_journal_entries(
    transaction: Any,
    ml_model: MLModel,
    top_k: int = 2,
) -> List[Dict[str, Any]]:
    """
    Suggest journal entry lines for a given transaction using a loaded MLModel.
    Returns debit and credit suggestions with accounts and probabilities.
    """
    if ml_model.name != "journal":
        raise ValueError("This model is not a journal model.")


    # Deserializa (modelo multi-label + MultiLabelBinarizer)
    model, mlb = joblib.load(io.BytesIO(ml_model.model_blob))

    fields = ml_model.prediction_fields or ["description", "amount"]
    row = _transaction_to_dict(transaction, fields)
    X_df = pd.DataFrame([row])

    # Probabilidade de cada classe ("debit:123" ou "credit:456")
    proba = model.predict_proba(X_df)[0] if hasattr(model, "predict_proba") else model.predict(X_df)[0].astype(float)
    labels = mlb.classes_

    # Separa e ordena rótulos por tipo (débito/crédito)
    debit_candidates: List[Tuple[str, float]] = []
    credit_candidates: List[Tuple[str, float]] = []
    for label, p in zip(labels, proba):
        if ":" in label:
            entry_type, acc_id = label.split(":", 1)
            if entry_type == "debit":
                debit_candidates.append((acc_id, p))
            elif entry_type == "credit":
                credit_candidates.append((acc_id, p))
    debit_candidates.sort(key=lambda x: x[1], reverse=True)
    credit_candidates.sort(key=lambda x: x[1], reverse=True)

    suggestions: List[List[Dict[str, Any]]] = []
    # Gera até top_k sugestões combinando i-ésimo débito com i-ésimo crédito
    for i in range(top_k):
        if i >= len(debit_candidates) and i >= len(credit_candidates):
            break
        suggestion: List[Dict[str, Any]] = []
        # Adiciona débito i, se existir
        if i < len(debit_candidates):
            acc_id, p = debit_candidates[i]
            suggestion.append(_build_entry_dict(acc_id, p, "debit"))
        # Adiciona crédito i, se existir
        if i < len(credit_candidates):
            acc_id, p = credit_candidates[i]
            suggestion.append(_build_entry_dict(acc_id, p, "credit"))
        suggestions.append(suggestion)

    return suggestions

def _build_entry_dict(account_id: str, prob: float, entry_type: str) -> Dict[str, Any]:
    acc_id_int = int(account_id)
    account_code = None
    account_name = None
    if Account is not None:
        try:
            acc = Account.objects.get(id=acc_id_int)
            account_code = acc.account_code
            account_name = acc.name
        except Account.DoesNotExist:
            pass
    return {
        "type": entry_type,
        "account_id": acc_id_int,
        "account_code": account_code,
        "account_name": account_name,
        "probability": float(prob),
    }
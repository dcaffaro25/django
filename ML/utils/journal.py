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
    row = {}
    for f in fields:
        if isinstance(tx, dict):
            row[f] = tx.get(f)
        else:
            row[f] = getattr(tx, f, None)
    return row

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

    model, mlb = joblib.load(io.BytesIO(ml_model.model_blob))

    fields = ml_model.prediction_fields or ["description", "amount"]
    row = _transaction_to_dict(transaction, fields)
    X_df = pd.DataFrame([row])

    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X_df)[0]
    else:
        proba = model.predict(X_df)[0]
        proba = proba.astype(float)

    labels = mlb.classes_
    sorted_indices = proba.argsort()[::-1][:top_k]
    suggestions: List[Dict[str, Any]] = []
    for idx in sorted_indices:
        label = labels[idx]
        prob = float(proba[idx])
        if ":" in label:
            entry_type, account_id_str = label.split(":", 1)
            account_id = int(account_id_str)
        else:
            entry_type = "unknown"
            account_id = None
        account_code = None
        account_name = None
        if Account is not None and account_id is not None:
            try:
                account = Account.objects.get(id=account_id)
                account_code = account.account_code
                account_name = account.name
            except Account.DoesNotExist:
                pass
        suggestions.append(
            {
                "type": entry_type,
                "account_id": account_id,
                "account_code": account_code,
                "account_name": account_name,
                "probability": prob,
            }
        )
    return suggestions

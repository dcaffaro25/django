import io
import joblib
import pandas as pd
from typing import Any, Dict, List, Tuple, Optional

from ML.models import MLModel

try:
    from accounting.models import Account
except Exception:
    Account = None  # type: ignore

def _transaction_to_dict(tx: Any, fields: List[str]) -> Dict[str, Any]:
    """
    Build a dict from a transaction object or dict using only the specified fields.
    """
    row = {}
    for field in fields:
        if isinstance(tx, dict):
            row[field] = tx.get(field)
        else:
            row[field] = getattr(tx, field, None)
    return row

def predict_top_accounts_with_names(
    transaction: Any,
    ml_model: MLModel,
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """
    Predict the most likely accounts for a given transaction using a loaded MLModel.
    Returns account IDs, codes, names and probabilities sorted by probability.
    """
    if ml_model.name != "categorization":
        raise ValueError("This model is not a categorisation model.")

    model = joblib.load(io.BytesIO(ml_model.model_blob))

    # Use prediction fields from metadata
    fields = ml_model.prediction_fields or ["description", "amount"]
    row = _transaction_to_dict(transaction, fields)
    df = pd.DataFrame([row])

    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(df)[0]
        classes = model.classes_
        sorted_indices = proba.argsort()[::-1][:top_n]
        predictions = []
        for idx in sorted_indices:
            account_id = int(classes[idx])
            prob = float(proba[idx])
            account_code = None
            account_name = None
            if Account is not None:
                try:
                    account = Account.objects.get(id=account_id)
                    account_code = account.account_code
                    account_name = account.name
                except Account.DoesNotExist:
                    pass
            predictions.append(
                {
                    "account_id": account_id,
                    "account_code": account_code,
                    "account_name": account_name,
                    "probability": prob,
                }
            )
        return predictions
    else:
        # fallback if model does not support predict_proba
        account_id = int(model.predict(df)[0])
        account_code = None
        account_name = None
        if Account is not None:
            try:
                account = Account.objects.get(id=account_id)
                account_code = account.account_code
                account_name = account.name
            except Account.DoesNotExist:
                pass
        return [
            {
                "account_id": account_id,
                "account_code": account_code,
                "account_name": account_name,
                "probability": 1.0,
            }
        ]

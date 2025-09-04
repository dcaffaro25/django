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
) -> List[List[Dict[str, Any]]]:
    """
    Sugere combinações de lançamentos (débitos/créditos) para uma transação com base
    em um modelo de label powerset. Retorna até top_k grupos de lançamentos.
    """
    if ml_model.name != "journal":
        raise ValueError("This model is not a journal model.")

    model, comb_map = joblib.load(io.BytesIO(ml_model.model_blob))

    fields = ml_model.prediction_fields or ["description", "amount"]
    row = {f: transaction.get(f) if isinstance(transaction, dict) else getattr(transaction, f, None) for f in fields}
    X_df = pd.DataFrame([row])

    # Distribuição de probabilidade entre as combinações aprendidas
    proba = model.predict_proba(X_df)[0]
    classes = model.classes_

    # Seleciona as top_k classes mais prováveis
    top_indices = np.argsort(-proba)[:top_k]
    suggestions: List[List[Dict[str, Any]]] = []

    for idx in top_indices:
        combo = classes[idx]
        labels = comb_map[combo]  # Ex.: ["debit:400","credit:1202","debit:500"]
        entries: List[Dict[str, Any]] = []
        for lbl in labels:
            entry_type, acc_id_str = lbl.split(":", 1)
            acc_id = int(acc_id_str)
            account_code = account_name = None
            if Account is not None:
                try:
                    acc_obj = Account.objects.get(id=acc_id)
                    account_code = acc_obj.account_code
                    account_name = acc_obj.name
                except Account.DoesNotExist:
                    pass
            entries.append({
                "type": entry_type,
                "account_id": acc_id,
                "account_code": account_code,
                "account_name": account_name,
                # probabilidade do grupo pode ser a probabilidade da classe ou
                # pode-se calcular um "score" agregado para cada entrada se desejar
            })
        suggestions.append(entries)

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
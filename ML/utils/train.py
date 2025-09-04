import io
import joblib
from typing import List, Dict, Any, Optional
from collections import Counter

import pandas as pd
from django.utils import timezone
from django.db.models import Q

from ML.models import MLModel
from .feature_extraction import build_classification_model
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, confusion_matrix


try:
    from accounting.models import Account, JournalEntry, Transaction
except Exception:
    Account = None
    JournalEntry = None
    Transaction = None

def _collect_training_samples(
    company_id: int,
    records_per_account: int = 100,
    include_pending: bool = False,
    training_fields: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Collect the most recent transactions for each leaf account in the company,
    returning a DataFrame with specified training fields and a 'label' column.
    """
    if Account is None or JournalEntry is None or Transaction is None:
        raise RuntimeError("Accounting models are unavailable.")

    if training_fields is None:
        training_fields = ["description", "amount"]

    # Base query: posted (and optionally pending) entries
    entry_qs = JournalEntry.objects.filter(
        account__company_id=company_id,
        account__is_active=True,
    ).select_related("transaction", "account")

    if include_pending:
        entry_qs = entry_qs.filter(
            Q(state="posted") | Q(state="pending"),
            Q(transaction__state="posted") | Q(transaction__state="pending"),
        )
    else:
        entry_qs = entry_qs.filter(state="posted", transaction__state="posted")

    leaf_accounts = (
        Account.objects.filter(company_id=company_id, is_active=True)
        .filter(children__isnull=True)
        .values_list("id", flat=True)
    )

    samples: List[Dict[str, Any]] = []
    for account_id in leaf_accounts:
        qs = (
            entry_qs.filter(account_id=account_id)
            .order_by("-transaction__date")[:records_per_account]
        )
        for entry in qs:
            tx = entry.transaction
            if not tx:
                continue
            row: Dict[str, Any] = {}

            # Constrói texto combinado: descrição da transação + atributos da conta
            if "description" in training_fields:
                parts = [
                    getattr(tx, "description", "") or "",
                    getattr(entry.account, "description", "") or "",
                    getattr(entry.account, "key_words", "") or "",
                    getattr(entry.account, "examples", "") or "",
                ]
                combined = " ".join([p for p in parts if p])
                row["description"] = combined

            # Copia outros campos numéricos
            for field in training_fields:
                if field == "description":
                    continue
                row[field] = getattr(tx, field) if hasattr(tx, field) else None

            row["label"] = account_id
            samples.append(row)

    return pd.DataFrame(samples)

def train_categorization_model(
    company_id: int,
    records_per_account: int = 100,
    training_fields: Optional[List[str]] = None,
    prediction_fields: Optional[List[str]] = None,
    include_pending: bool = True,
) -> MLModel:
    """
    Train a categorisation model and store it in MLModel.
    """
    if training_fields is None:
        training_fields = ["description", "amount"]
    if prediction_fields is None:
        prediction_fields = ["description", "amount"]

    df = _collect_training_samples(
        company_id=company_id,
        records_per_account=records_per_account,
        include_pending=include_pending,
        training_fields=training_fields,
    )
    if df.empty:
        raise RuntimeError("No training data found.")

    X = df[training_fields]
    y = df["label"]

    # Divisão treino/validação para calcular métricas (usa estratificação se possível)
    
    # Se alguma classe tiver apenas 1 amostra, duplica essa amostra
    class_counts = Counter(y)
    for label, count in class_counts.items():
        if count == 1:
            extra_rows = df[df["label"] == label].copy()
            X = pd.concat([X, extra_rows[training_fields]], ignore_index=True)
            y = pd.concat([y, extra_rows["label"]], ignore_index=True)

    # Tentativa de split estratificado; fallback caso falhe
    try:

        stratify = y if len(set(y)) > 1 else None
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=stratify
        )
    except ValueError:
        # Dataset muito pequeno / classes isoladas: treina com todo o conjunto
        X_train, y_train = X, y
        X_val = pd.DataFrame()
        y_val = pd.Series(dtype=y.dtype)
        
    model = build_classification_model()
    model.fit(X_train, y_train)

    # Cálculo de métricas na validação
    accuracy = None
    conf = None
    if len(X_val) > 0:
        y_pred = model.predict(X_val)
        accuracy = float(accuracy_score(y_val, y_pred))
        conf = confusion_matrix(y_val, y_pred, labels=model.classes_).tolist()

    # Versionamento: incrementa versão por companhia/nome de modelo
    last = (
        MLModel.objects.filter(company_id=company_id, name="categorization")
        .order_by("-version")
        .first()
    )
    version = (last.version + 1) if last else 1

    buffer = io.BytesIO()
    joblib.dump(model, buffer)
    buffer.seek(0)

    ml_record = MLModel.objects.create(
        company_id=company_id,
        name="categorization",
        model_type="classification",
        version=version,
        trained_at=timezone.now(),
        model_blob=buffer.read(),
        training_fields=training_fields,
        prediction_fields=prediction_fields,
        records_per_account=records_per_account,
        training_metrics={"accuracy": accuracy, "confusion_matrix": conf} if accuracy is not None else None,
    )
    return ml_record

def _assemble_journal_training_data(
    company_id: int,
    max_records: int = 1000,
    include_pending: bool = False,
    training_fields: Optional[List[str]] = None,
) -> (pd.DataFrame, List[List[str]]):
    """
    Build a DataFrame of transactions and a list of label lists
    (debit:<account_id>, credit:<account_id>) for journal predictions.
    Only the specified training_fields are used in X.
    """
    if Account is None or JournalEntry is None or Transaction is None:
        raise RuntimeError("Accounting models are unavailable.")

    if training_fields is None:
        training_fields = ["description", "amount"]

    tx_qs = (
        Transaction.objects.filter(company_id=company_id)
        .select_related()
        .prefetch_related("journal_entries")
        .order_by("-date")
    )
    if not include_pending:
        tx_qs = tx_qs.filter(state="posted")

    X_rows: List[Dict[str, Any]] = []
    y_labels: List[List[str]] = []

    for tx in tx_qs[:max_records]:
        entries = list(tx.journal_entries.all())
        if not entries or len(entries) > 4:
            continue
        labels = []
        for entry in entries:
            if entry.debit_amount:
                labels.append(f"debit:{entry.account_id}")
            elif entry.credit_amount:
                labels.append(f"credit:{entry.account_id}")
        if not labels:
            continue
        row = {}
        for field in training_fields:
            row[field] = getattr(tx, field) if hasattr(tx, field) else None
        X_rows.append(row)
        y_labels.append(labels)

    df = pd.DataFrame(X_rows)
    return df, y_labels

from collections import Counter
from sklearn.preprocessing import MultiLabelBinarizer, StandardScaler
from sklearn.multiclass import OneVsRestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer

def train_journal_model(
    company_id: int,
    records_per_account: int = 100,
    training_fields: Optional[List[str]] = None,
    prediction_fields: Optional[List[str]] = None,
    include_pending: bool = False,
) -> MLModel:
    if training_fields is None:
        training_fields = ["description", "amount"]
    if prediction_fields is None:
        prediction_fields = ["description", "amount"]

    # Extrai transações e listas de labels ["debit:400", "credit:1202", ...]
    X_df, y_labels = _assemble_journal_training_data(
        company_id=company_id,
        max_records=records_per_account,
        include_pending=include_pending,
        training_fields=training_fields,
    )
    if X_df.empty or not y_labels:
        raise RuntimeError("No journal training data available.")

    # Constrói uma label powerset: cada combinação vira uma string única
    # e mapeamos de volta para lista de labels
    comb_map: Dict[str, List[str]] = {}
    y_comb: List[str] = []
    for lbls in y_labels:
        combo = "|".join(sorted(lbls))
        comb_map[combo] = lbls
        y_comb.append(combo)

    preprocessor = ColumnTransformer(
        transformers=[
            ("text", TfidfVectorizer(stop_words="english", max_features=5000), "description"),
            ("num", StandardScaler(), ["amount"]),
        ],
        remainder="drop",
    )
    classifier = LogisticRegression(max_iter=200, solver="lbfgs", multi_class="multinomial")
    model = Pipeline([
        ("preprocessor", preprocessor),
        ("classifier", classifier),
    ])

    model.fit(X_df, y_comb)

    # Versionamento e armazenamento
    last = (
        MLModel.objects.filter(company_id=company_id, name="journal")
        .order_by("-version")
        .first()
    )
    version = (last.version + 1) if last else 1

    buffer = io.BytesIO()
    # Serializamos (classificador, mapping de classes)
    joblib.dump((model, comb_map), buffer)
    buffer.seek(0)

    ml_record = MLModel.objects.create(
        company_id=company_id,
        name="journal",
        model_type="multiclass-powerset",
        version=version,
        trained_at=timezone.now(),
        model_blob=buffer.read(),
        training_fields=training_fields,
        prediction_fields=prediction_fields,
        records_per_account=records_per_account,
    )
    return ml_record

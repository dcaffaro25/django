"""
Basic feature extraction for the categorisation model.

We use a TF‑IDF vectoriser for text fields (e.g. `description`) and a
standard scaler for numeric fields (e.g. `amount`).  You can extend this
module if you introduce new fields.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression

def build_preprocessor(text_column: str = "description", numeric_columns=None):
    if numeric_columns is None:
        numeric_columns = ["amount"]

    text_transformer = TfidfVectorizer(
        stop_words="english",
        max_features=10000,
        lowercase=True,
    )
    numeric_transformer = Pipeline(steps=[("scale", StandardScaler())])

    preprocessor = ColumnTransformer(
        transformers=[
            ("text", text_transformer, text_column),
            ("num", numeric_transformer, numeric_columns),
        ],
        remainder="drop",
    )
    return preprocessor

def build_classification_model():
    preprocessor = build_preprocessor()
    classifier = LogisticRegression(
        max_iter=1000,
        solver="lbfgs",
        n_jobs=-1,
        multi_class="auto",
    )
    model = Pipeline([
        ("preprocessor", preprocessor),
        ("classifier", classifier),
    ])
    return model

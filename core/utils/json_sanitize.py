# core/utils/json_sanitize.py
import math
from decimal import Decimal
try:
    import pandas as pd
    import numpy as np
except Exception:
    pd = None
    np = None

def json_nullsafe(value):
    # Floats
    if isinstance(value, float):
        return value if math.isfinite(value) else None

    # Decimals (handle NaN/Inf)
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None

    # Pandas DataFrame / Series
    if pd is not None:
        if isinstance(value, pd.DataFrame):
            df = value.copy()
            if np is not None:
                df = df.replace({np.nan: None, np.inf: None, -np.inf: None})
            else:
                df = df.where(df.notna(), None)
            return [json_nullsafe(r) for r in df.to_dict(orient="records")]
        if isinstance(value, pd.Series):
            s = value.copy()
            if np is not None:
                s = s.replace({np.nan: None, np.inf: None, -np.inf: None})
            else:
                s = s.where(s.notna(), None)
            return json_nullsafe(s.to_dict())

    # Lists / Tuples
    if isinstance(value, (list, tuple)):
        return [json_nullsafe(v) for v in value]

    # Dicts
    if isinstance(value, dict):
        return {k: json_nullsafe(v) for k, v in value.items()}

    return value

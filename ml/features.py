"""Shared feature engineering for training (ml/train.py) and serving (model-server).

Both sides must turn a raw IEEE-CIS row into exactly the same columns,
so this file is the single source of truth.
"""
import numpy as np
import pandas as pd

NUMERIC = [
    "TransactionAmt", "card1", "card2", "card3", "card5", "addr1", "addr2", "dist1",
    "C1", "C2", "C4", "C5", "C6", "C9", "C11", "C12", "C13", "C14",
    "D1", "D4", "D10", "D15",
]
CATEGORICAL = [
    "ProductCD", "card4", "card6", "P_emaildomain", "R_emaildomain", "DeviceType", "M4",
]
ENGINEERED = ["hour", "day_of_week", "amt_log", "amt_cents"]

# Features the monitor checks for drift (must exist in the raw order payload).
DRIFT_NUMERIC = ["TransactionAmt", "C1", "D1"]
DRIFT_CATEGORICAL = ["P_emaildomain", "DeviceType", "ProductCD"]

FEATURE_COLUMNS = NUMERIC + CATEGORICAL + ENGINEERED


def fit_category_maps(df: pd.DataFrame) -> dict:
    """Frequency encoding: each category becomes its share of the training rows."""
    maps = {}
    for col in CATEGORICAL:
        if col in df:
            maps[col] = df[col].fillna("unknown").value_counts(normalize=True).to_dict()
    return maps


def prepare(df: pd.DataFrame, category_maps: dict) -> pd.DataFrame:
    """Raw rows -> model input. Missing columns become NaN (LightGBM handles NaN)."""
    out = pd.DataFrame(index=df.index)
    for col in NUMERIC:
        out[col] = pd.to_numeric(df[col], errors="coerce") if col in df else np.nan
    for col in CATEGORICAL:
        values = df[col].fillna("unknown") if col in df else pd.Series("unknown", index=df.index)
        out[col] = values.map(category_maps.get(col, {})).astype(float)  # unseen -> NaN

    dt = pd.to_numeric(df.get("TransactionDT", pd.Series(np.nan, index=df.index)), errors="coerce")
    out["hour"] = (dt // 3600) % 24
    out["day_of_week"] = (dt // 86400) % 7
    amt = out["TransactionAmt"]
    out["amt_log"] = np.log1p(amt)
    out["amt_cents"] = (amt - np.floor(amt)).round(2)
    return out[FEATURE_COLUMNS]

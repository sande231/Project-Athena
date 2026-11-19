"""Drift detection with the Population Stability Index (PSI).

PSI < 0.1  : no real change
0.1 - 0.2  : moderate change, watch it
> 0.2      : significant drift -> alert
"""
import numpy as np

EPS = 1e-6


def numeric_reference(values, bins: int = 10) -> dict:
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    edges = np.unique(np.quantile(values, np.linspace(0, 1, bins + 1)))
    counts, _ = np.histogram(values, bins=edges)
    return {"type": "numeric", "edges": edges.tolist(), "expected": (counts / counts.sum()).tolist()}


def categorical_reference(values, top: int = 10) -> dict:
    values = ["unknown" if v is None or v != v else str(v) for v in values]
    cats, counts = np.unique(values, return_counts=True)
    order = np.argsort(-counts)[:top]
    shares = {str(cats[i]): counts[i] / len(values) for i in order}
    shares["__other__"] = max(0.0, 1 - sum(shares.values()))
    return {"type": "categorical", "expected": shares}


def psi(reference: dict, values) -> float:
    if reference["type"] == "numeric":
        arr = np.asarray([v for v in values if v is not None], dtype=float)
        arr = arr[~np.isnan(arr)]
        if len(arr) == 0:
            return 0.0
        edges = np.asarray(reference["edges"])
        arr = np.clip(arr, edges[0], edges[-1])
        counts, _ = np.histogram(arr, bins=edges)
        actual = counts / max(counts.sum(), 1)
        expected = np.asarray(reference["expected"])
    else:
        expected_map = reference["expected"]
        values = ["unknown" if v is None or v != v else str(v) for v in values]
        if not values:
            return 0.0
        keys = list(expected_map.keys())
        actual = np.zeros(len(keys))
        for v in values:
            actual[keys.index(v) if v in expected_map else keys.index("__other__")] += 1
        actual = actual / len(values)
        expected = np.asarray([expected_map[k] for k in keys])

    actual = np.clip(actual, EPS, None)
    expected = np.clip(expected, EPS, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))

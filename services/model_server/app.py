"""model-server: loads the trained model and returns fraud scores.

POST /predict  {"transaction": {...raw IEEE-CIS columns...}}
            -> {"score": 0.86, "top_features": [{"feature": "...", "value": ..., "impact": ...}], "model_version": "..."}
"""
import os
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

import features as F

MODEL_PATH = Path(os.getenv("MODEL_PATH", "ml/artifacts/model.joblib"))

app = Flask(__name__)
PREDICTIONS = Counter("athena_model_predictions_total", "Predictions served", ["decision_band"])
LATENCY = Histogram("athena_model_latency_seconds", "Prediction latency")
ERRORS = Counter("athena_model_errors_total", "Prediction errors")

bundle = None
if MODEL_PATH.exists():
    bundle = joblib.load(MODEL_PATH)
    MODEL_VERSION = f"{MODEL_PATH.name}@{int(MODEL_PATH.stat().st_mtime)}"
else:
    MODEL_VERSION = "dev-heuristic"
    print(f"WARNING: {MODEL_PATH} not found, using a simple heuristic until a model is trained")


def heuristic(row: pd.Series) -> tuple[float, list]:
    """Placeholder so the system runs before the real model exists. Not a fraud model."""
    amt = float(row.get("TransactionAmt") or 0)
    score = min(0.95, amt / 2000)
    return score, [{"feature": "TransactionAmt", "value": amt, "impact": round(score, 3)}]


@app.post("/predict")
def predict():
    start = time.perf_counter()
    try:
        tx = request.get_json(force=True).get("transaction", {})
        raw = pd.DataFrame([tx])
        if bundle is None:
            score, top = heuristic(raw.iloc[0])
        else:
            X = F.prepare(raw, bundle["category_maps"])
            model = bundle["model"]
            score = float(model.predict_proba(X)[0, 1])
            # per-feature contributions for this one prediction (last value is the bias term)
            contrib = model.booster_.predict(X, pred_contrib=True)[0][:-1]
            order = np.argsort(-np.abs(contrib))[:5]
            top = [{"feature": X.columns[i], "value": None if pd.isna(X.iloc[0, i]) else float(X.iloc[0, i]),
                    "impact": round(float(contrib[i]), 4)} for i in order]
        band = "block" if score >= 0.7 else "review" if score >= 0.3 else "approve"
        PREDICTIONS.labels(band).inc()
        return jsonify({"score": round(score, 4), "top_features": top, "model_version": MODEL_VERSION})
    except Exception as exc:  # keep serving; report the error
        ERRORS.inc()
        return jsonify({"error": str(exc)}), 400
    finally:
        LATENCY.observe(time.perf_counter() - start)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "model_version": MODEL_VERSION}


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8001)))

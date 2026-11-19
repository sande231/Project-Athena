"""athena-api: the one entry point for orders, decisions, labels and alerts.

See docs/ for the full endpoint list. Two-week scope endpoints are implemented here;
the rest are marked TODO.
"""
import os
import time

import requests
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from models import Alert, Base, Label, Prediction, Transaction

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///athena-dev.db")
MODEL_URL = os.getenv("MODEL_URL", "http://localhost:8001")
AI_URL = os.getenv("AI_URL", "http://localhost:8002")
REVIEW_AT = float(os.getenv("THRESHOLD_REVIEW", 0.3))
BLOCK_AT = float(os.getenv("THRESHOLD_BLOCK", 0.7))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base.metadata.create_all(engine)

app = Flask(__name__)
ORDERS = Counter("athena_orders_total", "Orders scored", ["decision"])
ORDER_LATENCY = Histogram("athena_order_latency_seconds", "End-to-end scoring latency")
UPSTREAM_ERRORS = Counter("athena_upstream_errors_total", "Failed calls to other services", ["service"])


def decide(score: float) -> str:
    return "block" if score >= BLOCK_AT else "review" if score >= REVIEW_AT else "approve"


def to_dict(tx: Transaction) -> dict:
    p = tx.prediction
    return {
        "id": tx.id, "order_id": tx.external_order_id, "store_id": tx.store_id, "amount": tx.amount,
        "created_at": tx.created_at.isoformat(), "features": tx.features,
        "score": p.score if p else None, "decision": p.decision if p else None,
        "reason": p.reason if p else None, "model_version": p.model_version if p else None,
        "label": None if tx.label is None else ("fraud" if tx.label.is_fraud else "legit"),
    }


@app.post("/api/transactions")
def score_transaction():
    start = time.perf_counter()
    body = request.get_json(force=True)
    features = body.get("transaction", body)

    try:
        pred = requests.post(f"{MODEL_URL}/predict", json={"transaction": features}, timeout=5).json()
        score = pred["score"]
    except Exception:
        UPSTREAM_ERRORS.labels("model-server").inc()
        return jsonify({"error": "model-server unavailable"}), 503

    decision = decide(score)
    reason = None
    if decision != "approve":
        try:
            reason = requests.post(f"{AI_URL}/explain-order", timeout=10, json={
                "score": score, "decision": decision, "top_features": pred.get("top_features", [])}).json()["reason"]
        except Exception:
            UPSTREAM_ERRORS.labels("ai-service").inc()
            reason = "Flagged by the fraud model."

    latency_ms = (time.perf_counter() - start) * 1000
    with Session(engine) as s:
        tx = Transaction(external_order_id=str(body.get("order_id") or features.get("TransactionID") or ""),
                         store_id=body.get("store_id", "demo-store"),
                         amount=features.get("TransactionAmt"), features=features)
        tx.prediction = Prediction(model_version=pred.get("model_version", "unknown"), score=score,
                                   decision=decision, reason=reason, latency_ms=latency_ms)
        s.add(tx)
        s.commit()
        tx_id = tx.id

    ORDERS.labels(decision).inc()
    ORDER_LATENCY.observe(latency_ms / 1000)
    return jsonify({"id": tx_id, "score": score, "decision": decision, "reason": reason,
                    "latency_ms": round(latency_ms, 1)})


@app.get("/api/transactions")
def list_transactions():
    decision = request.args.get("decision")
    limit = min(int(request.args.get("limit", 50)), 1000)
    with Session(engine) as s:
        q = select(Transaction).join(Prediction).order_by(Transaction.id.desc()).limit(limit)
        if decision:
            q = q.where(Prediction.decision == decision)
        return jsonify([to_dict(tx) for tx in s.scalars(q)])


@app.patch("/api/transactions/<int:tx_id>/label")
def label_transaction(tx_id: int):
    is_fraud = bool(request.get_json(force=True)["is_fraud"])
    with Session(engine) as s:
        tx = s.get(Transaction, tx_id)
        if tx is None:
            return jsonify({"error": "not found"}), 404
        if tx.label:
            tx.label.is_fraud = is_fraud
        else:
            tx.label = Label(is_fraud=is_fraud)
        s.commit()
    return jsonify({"id": tx_id, "label": "fraud" if is_fraud else "legit"})


@app.get("/api/metrics/summary")
def metrics_summary():
    with Session(engine) as s:
        rows = s.execute(select(Prediction.decision, func.count(), func.avg(Prediction.latency_ms))
                         .group_by(Prediction.decision)).all()
        counts = {d: c for d, c, _ in rows}
        total = sum(counts.values())
        avg_latency = (sum(c * (l or 0) for _, c, l in rows) / total) if total else 0
        labeled = s.execute(select(Prediction.decision, Label.is_fraud)
                            .join(Label, Label.transaction_id == Prediction.transaction_id)).all()
    tp = sum(1 for d, f in labeled if d == "block" and f)
    fp = sum(1 for d, f in labeled if d == "block" and not f)
    fn = sum(1 for d, f in labeled if d != "block" and f)
    return jsonify({
        "orders": total, "approved": counts.get("approve", 0), "review": counts.get("review", 0),
        "blocked": counts.get("block", 0),
        "flag_rate": round((counts.get("review", 0) + counts.get("block", 0)) / total, 4) if total else 0,
        "avg_latency_ms": round(avg_latency, 1), "labeled": len(labeled),
        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "recall": round(tp / (tp + fn), 4) if tp + fn else None,
    })


@app.get("/api/alerts")
def list_alerts():
    with Session(engine) as s:
        alerts = s.scalars(select(Alert).order_by(Alert.id.desc()).limit(50))
        return jsonify([{"id": a.id, "type": a.type, "severity": a.severity, "status": a.status,
                         "created_at": a.created_at.isoformat(), "metrics": a.metric_snapshot,
                         "explanation": a.ai_explanation} for a in alerts])


@app.post("/api/alerts")
def create_alert():
    """Called by monitor-worker."""
    body = request.get_json(force=True)
    with Session(engine) as s:
        a = Alert(type=body["type"], severity=body.get("severity", "warning"),
                  metric_snapshot=body.get("metrics", {}), ai_explanation=body.get("explanation", {}))
        s.add(a)
        s.commit()
        return jsonify({"id": a.id}), 201


@app.post("/api/retrain")
def retrain():
    # TODO (ML + DevOps): start a Kubernetes Job that runs ml/train.py and writes to the artifacts volume
    return jsonify({"status": "accepted", "note": "retraining job not wired yet"}), 202


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

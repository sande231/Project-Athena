"""API tests. Run from the repo root:  pytest -q
Uses SQLite and fakes the model-server and ai-service, so no other service is needed."""
import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(ROOT / "ml"))


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
app_module = importlib.import_module("app")


@pytest.fixture
def client(monkeypatch):
    # fresh empty tables for every test
    app_module.Base.metadata.drop_all(app_module.engine)
    app_module.Base.metadata.create_all(app_module.engine)

    def fake_post(url, json=None, timeout=None):
        if url.endswith("/predict"):
            amount = json["transaction"].get("TransactionAmt", 0)
            return FakeResponse({"score": 0.9 if amount > 500 else 0.05, "model_version": "test",
                                 "top_features": [{"feature": "TransactionAmt", "value": amount, "impact": 1.0}]})
        return FakeResponse({"reason": "Unusually large amount."})

    monkeypatch.setattr(app_module.requests, "post", fake_post)
    return app_module.app.test_client()


def test_health(client):
    assert client.get("/healthz").json["status"] == "ok"


def test_low_amount_is_approved(client):
    r = client.post("/api/transactions", json={"transaction": {"TransactionAmt": 20}}).json
    assert r["decision"] == "approve" and r["reason"] is None


def test_high_amount_is_blocked_with_reason(client):
    r = client.post("/api/transactions", json={"transaction": {"TransactionAmt": 900}}).json
    assert r["decision"] == "block"
    assert r["reason"] == "Unusually large amount."


def test_label_and_summary(client):
    tx_id = client.post("/api/transactions", json={"transaction": {"TransactionAmt": 900}}).json["id"]
    assert client.patch(f"/api/transactions/{tx_id}/label", json={"is_fraud": True}).status_code == 200
    s = client.get("/api/metrics/summary").json
    assert s["orders"] == 1 and s["blocked"] == 1 and s["precision"] == 1.0


def test_alerts_roundtrip(client):
    client.post("/api/alerts", json={"type": "drift", "metrics": {"psi": {"x": 0.4}},
                                     "explanation": {"summary": "Drift found."}})
    assert client.get("/api/alerts").json[0]["explanation"]["summary"] == "Drift found."


def test_psi_detects_shift():
    import drift
    ref = drift.numeric_reference(list(range(1000)))
    assert drift.psi(ref, list(range(1000))) < 0.05
    assert drift.psi(ref, [900] * 500) > 0.2

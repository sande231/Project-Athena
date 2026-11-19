"""monitor-worker: every CHECK_INTERVAL seconds, compare recent orders with the training data.

If any key feature drifts (PSI > 0.2) or the flag rate jumps, it asks ai-service for a
plain-English explanation and posts an alert to athena-api.
"""
import json
import os
import time

import requests

import drift

API_URL = os.getenv("API_URL", "http://localhost:8000")
AI_URL = os.getenv("AI_URL", "http://localhost:8002")
REFERENCE_PATH = os.getenv("REFERENCE_PATH", "ml/artifacts/reference_stats.json")
INTERVAL = int(os.getenv("CHECK_INTERVAL", 60))
WINDOW = int(os.getenv("WINDOW", 300))           # number of recent orders to check
PSI_ALERT = float(os.getenv("PSI_ALERT", 0.2))
MIN_ORDERS = 50


def check_once(reference: dict, last_alert: dict) -> None:
    orders = requests.get(f"{API_URL}/api/transactions", params={"limit": WINDOW}, timeout=10).json()
    if len(orders) < MIN_ORDERS:
        print(f"only {len(orders)} orders, waiting")
        return

    scores = {feat: round(drift.psi(ref, [o["features"].get(feat) for o in orders]), 3)
              for feat, ref in reference.items()}
    summary = requests.get(f"{API_URL}/api/metrics/summary", timeout=10).json()
    drifted = {k: v for k, v in scores.items() if v > PSI_ALERT}
    print("psi:", scores)

    if not drifted:
        return
    key = ",".join(sorted(drifted))
    if last_alert.get("key") == key and time.time() - last_alert.get("at", 0) < 15 * 60:
        return  # do not repeat the same alert within 15 minutes

    explanation = requests.post(f"{AI_URL}/explain-alert", timeout=30, json={
        "alert_type": "data drift", "metrics": summary, "drift": scores}).json()
    severity = "critical" if max(drifted.values()) > 0.5 else "warning"
    requests.post(f"{API_URL}/api/alerts", timeout=10, json={
        "type": "drift", "severity": severity, "metrics": {"psi": scores, "summary": summary},
        "explanation": explanation})
    last_alert.update(key=key, at=time.time())
    print("ALERT:", json.dumps(explanation))


def main():
    while not os.path.exists(REFERENCE_PATH):
        print(f"waiting for {REFERENCE_PATH} (run ml/train.py first)")
        time.sleep(INTERVAL)
    reference = json.load(open(REFERENCE_PATH))
    last_alert: dict = {}
    while True:
        try:
            check_once(reference, last_alert)
        except Exception as exc:
            print("check failed:", exc)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

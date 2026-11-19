"""ai-service: every Claude (Anthropic API) call goes through here.

POST /explain-order  {"score", "decision", "top_features"}       -> {"reason"}
POST /explain-alert  {"alert_type", "metrics", "drift"}           -> {"summary", "likely_cause", "action"}

If ANTHROPIC_API_KEY is missing or the API fails, it returns a simple rule-based
answer so fraud decisions never depend on Claude being available.
"""
import json
import os

from flask import Flask, jsonify, request
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
CALLS = Counter("athena_ai_calls_total", "Claude calls", ["kind", "result"])

FAST_MODEL = os.getenv("CLAUDE_FAST_MODEL", "claude-haiku-5-5")
SMART_MODEL = os.getenv("CLAUDE_SMART_MODEL", "claude-sonnet-5-5")

client = None
if os.getenv("ANTHROPIC_API_KEY"):
    import anthropic
    client = anthropic.Anthropic()

ORDER_PROMPT = """You explain fraud-check results to a small online store owner who is not technical.
Score: {score} (0 = safe, 1 = almost certainly fraud). Decision: {decision}.
Top model features and their impact (positive = more suspicious):
{features}
Write ONE plain-English sentence (max 25 words) saying why this order was flagged.
No jargon, no feature codes like C1 or D1; describe them generally (e.g. "unusual activity on this card")."""

ALERT_PROMPT = """You are the monitoring assistant for a fraud-detection model.
Alert type: {alert_type}
Current metrics: {metrics}
Drift report (PSI per feature, > 0.2 means significant change): {drift}
Reply with JSON only: {{"summary": "...", "likely_cause": "...", "action": "..."}}
Each value is one short plain-English sentence. Do not invent numbers that are not given."""


def ask(model: str, prompt: str, max_tokens: int) -> str:
    msg = client.messages.create(model=model, max_tokens=max_tokens,
                                 messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text.strip()


@app.post("/explain-order")
def explain_order():
    body = request.get_json(force=True)
    top = body.get("top_features", [])
    fallback = "Flagged mainly because of: " + ", ".join(f["feature"] for f in top[:3]) if top else "Flagged by the fraud model."
    if client is None:
        CALLS.labels("order", "fallback").inc()
        return jsonify({"reason": fallback, "source": "rules"})
    try:
        feats = "\n".join(f"- {f['feature']} = {f['value']} (impact {f['impact']})" for f in top)
        reason = ask(FAST_MODEL, ORDER_PROMPT.format(score=body.get("score"), decision=body.get("decision"),
                                                     features=feats), 80)
        CALLS.labels("order", "ok").inc()
        return jsonify({"reason": reason, "source": "claude"})
    except Exception as exc:
        CALLS.labels("order", "error").inc()
        return jsonify({"reason": fallback, "source": "rules", "error": str(exc)})


@app.post("/explain-alert")
def explain_alert():
    body = request.get_json(force=True)
    drifted = [k for k, v in body.get("drift", {}).items() if v > 0.2]
    fallback = {"summary": f"{body.get('alert_type', 'Alert')}: changes detected in {', '.join(drifted) or 'model metrics'}.",
                "likely_cause": "Incoming orders look different from the training data.",
                "action": "Review flagged orders and consider retraining."}
    if client is None:
        CALLS.labels("alert", "fallback").inc()
        return jsonify({**fallback, "source": "rules"})
    try:
        text = ask(SMART_MODEL, ALERT_PROMPT.format(alert_type=body.get("alert_type"),
                                                    metrics=json.dumps(body.get("metrics", {})),
                                                    drift=json.dumps(body.get("drift", {}))), 300)
        result = json.loads(text[text.find("{"): text.rfind("}") + 1])
        CALLS.labels("alert", "ok").inc()
        return jsonify({**result, "source": "claude"})
    except Exception as exc:
        CALLS.labels("alert", "error").inc()
        return jsonify({**fallback, "source": "rules", "error": str(exc)})


@app.get("/healthz")
def healthz():
    return {"status": "ok", "claude": client is not None}


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8002)))

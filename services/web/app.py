"""athena-web: serves the frontend pages and forwards /api/* calls to athena-api,
so the browser talks to one address (no CORS setup needed)."""
import os

import requests
from flask import Flask, Response, request, send_from_directory

API_URL = os.getenv("API_URL", "http://localhost:8000")
STATIC = os.path.join(os.path.dirname(__file__), "static")

# Request headers passed through to athena-api. Content-Type is passed as sent, so
# JSON bodies and file uploads (multipart/form-data) both arrive intact.
FORWARD_HEADERS = ("Content-Type", "Authorization", "X-API-Key")

app = Flask(__name__, static_folder=None)


@app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def proxy(path):
    headers = {h: request.headers[h] for h in FORWARD_HEADERS if h in request.headers}
    upstream = requests.request(request.method, f"{API_URL}/api/{path}", params=request.args,
                                data=request.get_data(), headers=headers, timeout=30)
    return Response(upstream.content, upstream.status_code,
                    content_type=upstream.headers.get("Content-Type", "application/json"))


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/<path:name>")
def static_files(name):
    return send_from_directory(STATIC, name)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

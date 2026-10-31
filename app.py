"""Cloud Monitoring Demo - Flask API and dashboard."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from monitoring import (
    MAX_HOURS,
    cloudwatch_enabled,
    dashboard,
    region_name,
)

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional convenience dependency
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent
if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


@app.get("/")
def index():
    return render_template("index.html", max_hours=MAX_HOURS)


@app.get("/api/dashboard")
def api_dashboard():
    try:
        hours = int(request.args.get("hours", "24"))
    except ValueError:
        hours = 24

    source = request.args.get("source", "auto").lower()
    if source not in {"auto", "sample", "cloudwatch"}:
        source = "auto"

    instance_id = request.args.get("instance") or None
    payload = dashboard(hours=hours, instance_id=instance_id, source=source)
    return jsonify(payload)


@app.get("/api/config")
def api_config():
    return jsonify(
        {
            "cloudwatch_enabled": cloudwatch_enabled(),
            "region": region_name(),
            "max_hours": MAX_HOURS,
            "source": "cloudwatch" if cloudwatch_enabled() else "sample",
        }
    )


@app.get("/api/health")
def api_health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")

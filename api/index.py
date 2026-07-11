"""Vercel serverless entrypoint for AgroGuide.

This file intentionally catches import/startup errors so Vercel returns a
diagnostic JSON response instead of only FUNCTION_INVOCATION_FAILED.
"""
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from run import app  # noqa: E402

    @app.get("/_vercel_probe")
    def _vercel_probe():
        from flask import jsonify

        return jsonify(
            {
                "app": "imported",
                "vercel": bool(os.getenv("VERCEL")),
                "db_host_set": bool(os.getenv("DB_HOST")),
                "db_name_set": bool(os.getenv("DB_NAME")),
                "db_user_set": bool(os.getenv("DB_USER")),
                "db_password_set": bool(os.getenv("DB_PASSWORD")),
                "secret_key_set": bool(os.getenv("SECRET_KEY")),
                "model_api_url_set": bool(os.getenv("MODEL_API_URL")),
                "gemini_key_set": bool(os.getenv("GEMINI_API_KEY")),
                "search_key_set": bool(os.getenv("SEARCH_API_KEY")),
            }
        )

    @app.get("/_vercel_db_probe")
    def _vercel_db_probe():
        from flask import jsonify
        from sqlalchemy import text
        from app import db

        try:
            row = db.session.execute(text("SELECT current_database(), current_user")).one()
            return jsonify(
                {
                    "database": "ok",
                    "db_name": row[0],
                    "db_user": row[1],
                }
            )
        except Exception as db_exc:
            db.session.rollback()
            return jsonify(
                {
                    "database": "error",
                    "type": db_exc.__class__.__name__,
                    "message": str(db_exc)[:500],
                }
            ), 503
except Exception as exc:
    from flask import Flask, jsonify

    startup_error = {
        "error": "AgroGuide failed to start on Vercel.",
        "type": exc.__class__.__name__,
        "message": str(exc),
        "traceback_tail": traceback.format_exc().splitlines()[-8:],
    }

    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def _startup_failure(path):
        return jsonify(startup_error), 500

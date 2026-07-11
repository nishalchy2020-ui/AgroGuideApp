import logging
import os
import hmac
import secrets
import sys
from pathlib import Path

from flask import Flask, abort, jsonify, request, session
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"


def create_app(config_class=None):
    if config_class is None:
        from config import get_config

        config_class = get_config()

    config_class.validate()

    app = Flask(__name__)
    app.config.from_object(config_class)
    config_class.init_app(app)
    _configure_logging(app)

    # Vercel serverless filesystem is read-only except /tmp.
    # Therefore, uploaded files must be stored in /tmp/uploads on Vercel.
    if os.getenv("VERCEL"):
        app.config["UPLOAD_FOLDER"] = "/tmp/uploads"

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app.routes import register_blueprints

    register_blueprints(app)

    _log_config_status(app)
    _register_error_handlers(app)

    if app.config.get("AUTO_INIT_DB"):
        with app.app_context():
            db.create_all()
            from app.models import ensure_chatbot_message_schema

            ensure_chatbot_message_schema()
            _seed_defaults(app)
    else:
        app.logger.info(
            "AUTO_INIT_DB=false; expecting PostgreSQL schema to be applied from schema.sql."
        )

    return app


def _configure_logging(app):
    level_name = app.config.get("LOG_LEVEL", "INFO")
    level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(level)
    app.logger.setLevel(level)


def _register_error_handlers(app):
    @app.context_processor
    def _inject_csrf_token():
        return {"csrf_token": _csrf_token}

    @app.before_request
    def _log_request():
        app.logger.debug("%s %s", request.method, request.path)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            _validate_csrf()

    @app.teardown_request
    def _rollback_on_error(exc):
        if exc is not None:
            db.session.rollback()

    @app.errorhandler(400)
    def bad_request(error):
        return _error_response(error, 400)

    @app.errorhandler(404)
    def not_found(error):
        return _error_response(error, 404)

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        app.logger.exception("Unhandled server error: %s", error)
        return _error_response(error, 500)


def _csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def _validate_csrf():
    expected = session.get("_csrf_token")
    supplied = request.form.get("_csrf_token") or request.headers.get("X-CSRFToken")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        abort(400, description="Invalid or missing CSRF token.")


def _error_response(error, status_code):
    if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
        message = getattr(error, "description", "Server error")
        return jsonify({"error": message, "status": status_code}), status_code
    message = getattr(error, "description", "Server error")
    return message, status_code


def _log_config_status(app):
    logger = logging.getLogger("agroguide")

    if os.getenv("VERCEL"):
        logger.info("Running on Vercel. Upload folder set to /tmp/uploads.")

    if not app.config.get("SEARCH_API_KEY"):
        logger.info(
            "SEARCH_API_KEY not set - chatbot will use local AgroGuide knowledge only"
        )
    else:
        logger.info(
            "Hybrid chatbot search configured (provider=%s)",
            app.config.get("SEARCH_PROVIDER", "tavily"),
        )


def _seed_defaults(app):
    from app.models import DiseaseKnowledge, User
    from app.services.knowledge_service import get_builtin_knowledge
    from werkzeug.security import generate_password_hash

    try:
        if DiseaseKnowledge.query.count() == 0:
            for class_name, data in get_builtin_knowledge().items():
                db.session.add(
                    DiseaseKnowledge(
                        class_name=class_name,
                        description=data.get("description", ""),
                        symptoms=data.get("symptoms", ""),
                        causes=data.get("causes", ""),
                        treatment=data.get("treatment", ""),
                        prevention=data.get("prevention", ""),
                        severity=data.get("severity", "low"),
                        pesticide=data.get("pesticide", ""),
                        organic_solution=data.get("organic_solution", ""),
                    )
                )

        admin_email = app.config["DEFAULT_ADMIN_EMAIL"]

        if not User.query.filter_by(email=admin_email).first():
            db.session.add(
                User(
                    name="AgroGuide Admin",
                    email=admin_email,
                    password_hash=generate_password_hash(
                        app.config["DEFAULT_ADMIN_PASSWORD"]
                    ),
                    is_admin=True,
                ),
            )

        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Default seed failed.")
        raise

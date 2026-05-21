import logging
from pathlib import Path

from flask import Flask
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

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["ML_MODELS_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app.routes import register_blueprints

    register_blueprints(app)

    _log_config_status(app)

    with app.app_context():
        db.create_all()
        from app.models import ensure_chatbot_message_schema

        ensure_chatbot_message_schema()
        _seed_defaults(app)

    return app


def _log_config_status(app):
    logger = logging.getLogger("agroguide")
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
            )
        )

    db.session.commit()

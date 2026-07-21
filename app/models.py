import json
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import inspect, text

from app import db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_email_verified = db.Column(db.Boolean, nullable=False, default=False)
    email_verification_token = db.Column(db.String(128), nullable=True, index=True)
    email_verification_expires_at = db.Column(db.DateTime, nullable=True)
    password_reset_token = db.Column(db.String(128), nullable=True, index=True)
    password_reset_expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    scans = db.relationship(
        "ScanResult",
        backref="user",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    weather_searches = db.relationship(
        "WeatherSearch",
        backref="user",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    chat_messages = db.relationship(
        "ChatbotMessage",
        backref="user",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    admin_logs = db.relationship(
        "AdminLog",
        backref="admin",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    activities = db.relationship(
        "ActivityHistory",
        backref="user",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ScanResult(db.Model):
    __tablename__ = "scan_results"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    image_filename = db.Column(db.String(255), nullable=False)
    disease_class = db.Column(db.String(255), nullable=False)
    disease_label = db.Column(db.String(255), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    severity = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)


class WeatherSearch(db.Model):
    __tablename__ = "weather_searches"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    location_name = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    wind_speed = db.Column(db.Float)
    rainfall = db.Column(db.Float)
    farming_advice = db.Column(db.Text)
    disease_risk = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)


class ChatbotMessage(db.Model):
    __tablename__ = "chatbot_messages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = db.Column(db.String(16), nullable=False)
    message = db.Column(db.Text, nullable=True)
    content = db.Column(db.Text, nullable=False)
    source_type = db.Column(db.String(32), nullable=False, default="local")
    sources = db.Column(db.Text, nullable=False, default="[]")
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    @property
    def display_message(self):
        return self.message or self.content

    @property
    def display_sources(self):
        try:
            value = json.loads(self.sources or "[]")
        except (TypeError, ValueError):
            return []
        if not isinstance(value, list):
            return []

        sources = []
        for position, source in enumerate(value, start=1):
            if not isinstance(source, dict) or not source.get("name"):
                continue
            url = source.get("url") or None
            if url and not str(url).lower().startswith(("http://", "https://")):
                url = None
            sources.append(
                {
                    "index": source.get("index") or position,
                    "name": str(source["name"]),
                    "url": url,
                }
            )
        return sources

    def set_message(self, value):
        self.message = value
        self.content = value


class DiseaseKnowledge(db.Model):
    __tablename__ = "disease_knowledge"

    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(255), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, default="")
    symptoms = db.Column(db.Text, default="")
    causes = db.Column(db.Text, default="")
    treatment = db.Column(db.Text, default="")
    prevention = db.Column(db.Text, default="")
    severity = db.Column(db.String(32), default="low")
    pesticide = db.Column(db.Text, default="")
    organic_solution = db.Column(db.Text, default="")
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


class AdminLog(db.Model):
    __tablename__ = "admin_logs"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)


class ActivityHistory(db.Model):
    """Unified history for all AgroGuide modules."""

    __tablename__ = "activity_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    module = db.Column(db.String(64), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.Text, default="{}")
    ref_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)


def ensure_chatbot_message_schema():
    """Add chatbot history columns for existing databases."""
    inspector = inspect(db.engine)
    if "chatbot_messages" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("chatbot_messages")}
    if "message" not in columns:
        db.session.execute(text("ALTER TABLE chatbot_messages ADD COLUMN message TEXT"))
        db.session.execute(
            text("UPDATE chatbot_messages SET message = content WHERE message IS NULL")
        )
    if "source_type" not in columns:
        db.session.execute(
            text(
                "ALTER TABLE chatbot_messages "
                "ADD COLUMN source_type VARCHAR(32) NOT NULL DEFAULT 'local'"
            )
        )
    if "sources" not in columns:
        db.session.execute(
            text(
                "ALTER TABLE chatbot_messages "
                "ADD COLUMN sources TEXT NOT NULL DEFAULT '[]'"
            )
        )
    db.session.commit()


def ensure_user_security_schema():
    """Add auth security columns for existing databases."""
    inspector = inspect(db.engine)
    if "users" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    dialect = db.engine.dialect.name

    if "is_email_verified" not in columns:
        if dialect == "postgresql":
            db.session.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN IF NOT EXISTS is_email_verified BOOLEAN NOT NULL DEFAULT TRUE"
                )
            )
        else:
            db.session.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN is_email_verified BOOLEAN NOT NULL DEFAULT 1"
                )
            )

    column_specs = {
        "email_verification_token": "VARCHAR(128)",
        "email_verification_expires_at": "TIMESTAMP",
        "password_reset_token": "VARCHAR(128)",
        "password_reset_expires_at": "TIMESTAMP",
    }
    for column_name, column_type in column_specs.items():
        if column_name not in columns:
            if dialect == "postgresql":
                db.session.execute(
                    text(
                        f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
                    )
                )
            else:
                db.session.execute(
                    text(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                )

    if dialect == "postgresql":
        db.session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_users_email_verification_token "
                "ON users(email_verification_token)"
            )
        )
        db.session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_users_password_reset_token "
                "ON users(password_reset_token)"
            )
        )
    db.session.commit()

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
    created_at = db.Column(db.DateTime, default=utcnow)

    scans = db.relationship("ScanResult", backref="user", lazy="dynamic")
    weather_searches = db.relationship(
        "WeatherSearch", backref="user", lazy="dynamic"
    )
    chat_messages = db.relationship(
        "ChatbotMessage", backref="user", lazy="dynamic"
    )


class ScanResult(db.Model):
    __tablename__ = "scan_results"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    image_filename = db.Column(db.String(255), nullable=False)
    disease_class = db.Column(db.String(255), nullable=False)
    disease_label = db.Column(db.String(255), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    severity = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)


class WeatherSearch(db.Model):
    __tablename__ = "weather_searches"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
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
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String(16), nullable=False)
    message = db.Column(db.Text, nullable=True)
    content = db.Column(db.Text, nullable=False)
    source_type = db.Column(db.String(32), nullable=False, default="local")
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    @property
    def display_message(self):
        return self.message or self.content

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
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)


class ActivityHistory(db.Model):
    """Unified history for all AgroGuide modules."""

    __tablename__ = "activity_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    module = db.Column(db.String(64), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.Text, default="{}")
    ref_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    user = db.relationship("User", backref=db.backref("activities", lazy="dynamic"))


def ensure_chatbot_message_schema():
    """Add chatbot history columns for existing SQLite databases."""
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
    db.session.commit()

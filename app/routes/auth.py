import logging
import time
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models import User

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger("agroguide.auth")
_RATE_LIMITS = {}


def _is_safe_next(target):
    if not target:
        return False
    parsed = urlsplit(target)
    return not parsed.netloc and parsed.path.startswith("/")


def _rate_limited(scope, limit=5, window_seconds=300):
    now = time.time()
    bucket = _RATE_LIMITS.setdefault(scope, [])
    bucket[:] = [ts for ts in bucket if now - ts < window_seconds]
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


def _client_key(action, email=""):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    ip = ip.split(",", 1)[0].strip()
    return f"{action}:{ip}:{email.lower().strip()}"


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if _rate_limited(_client_key("register", email), limit=4):
            flash("Too many registration attempts. Please wait a few minutes.", "error")
            return render_template("auth/register.html"), 429

        if not name or not email or not password:
            flash("All fields are required.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            flash("Enter a valid email address.", "error")
        elif User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
        else:
            try:
                user = User(
                    name=name,
                    email=email,
                    password_hash=generate_password_hash(password),
                )
                db.session.add(user)
                db.session.commit()
                session.permanent = True
                login_user(user)
                flash("Welcome to AgroGuide!", "success")
                return redirect(url_for("main.dashboard"))
            except IntegrityError:
                db.session.rollback()
                flash("Email already registered.", "error")
            except SQLAlchemyError:
                db.session.rollback()
                logger.exception("Registration failed for email=%s", email)
                flash("Registration could not be completed. Please try again.", "error")

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if _rate_limited(_client_key("login", email), limit=6):
            flash("Too many login attempts. Please wait a few minutes.", "error")
            return render_template("auth/login.html"), 429
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session.permanent = True
            login_user(user, remember=bool(request.form.get("remember")))
            next_page = request.args.get("next")
            flash("Logged in successfully.", "success")
            if user.is_admin and request.form.get("admin_login"):
                return redirect(url_for("admin.dashboard"))
            return redirect(next_page if _is_safe_next(next_page) else url_for("main.dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))

import logging
import time
from datetime import timezone
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models import User
from app.models import utcnow
from app.services.email_service import (
    send_password_changed_email,
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
)
from app.services.token_service import expires_in, generate_token, hash_token, is_expired

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


def _client_ip():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    return ip.split(",", 1)[0].strip() or None


def _wants_json():
    return request.is_json or request.accept_mimetypes.best == "application/json"


def _auth_response(message, category="info", status=200, template=None, **context):
    if _wants_json():
        payload = {"message": message, "status": status}
        payload.update(context.pop("json_extra", {}))
        return jsonify(payload), status
    flash(message, category)
    if template:
        return render_template(template, **context), status
    return redirect(context.get("redirect_to") or url_for("auth.login"))


def _format_dt(value):
    if not value:
        return "Not available"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M UTC")


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
        else:
            try:
                if User.query.filter_by(email=email).first():
                    flash("Email already registered.", "error")
                    return render_template("auth/register.html")
                user = User(
                    name=name,
                    email=email,
                    password_hash=generate_password_hash(password),
                    is_email_verified=False,
                )
                raw_token, token_hash = generate_token()
                user.email_verification_token = token_hash
                user.email_verification_expires_at = expires_in(
                    current_app.config["EMAIL_VERIFICATION_TOKEN_MINUTES"]
                )
                db.session.add(user)
                db.session.commit()
                try:
                    send_verification_email(user, raw_token)
                except Exception:
                    logger.exception("Verification email failed for email=%s", email)
                message = "Registration successful. Please check your email to verify your account before logging in."
                return _auth_response(
                    message,
                    "success",
                    201,
                    template="auth/register.html",
                    json_extra={"email_verification_required": True},
                )
            except IntegrityError:
                db.session.rollback()
                flash("Email already registered.", "error")
            except SQLAlchemyError:
                db.session.rollback()
                logger.exception("Registration failed for email=%s", email)
                flash("Registration could not be completed. Please try again.", "error")
            except Exception:
                db.session.rollback()
                logger.exception("Unexpected registration failure for email=%s", email)
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
        try:
            user = User.query.filter_by(email=email).first()
        except SQLAlchemyError:
            db.session.rollback()
            logger.exception("Login database lookup failed for email=%s", email)
            flash("Login is temporarily unavailable. Please try again shortly.", "error")
            return render_template("auth/login.html"), 503
        except Exception:
            db.session.rollback()
            logger.exception("Unexpected login lookup failure for email=%s", email)
            flash("Login is temporarily unavailable. Please try again shortly.", "error")
            return render_template("auth/login.html"), 503

        if user and check_password_hash(user.password_hash, password):
            if not user.is_email_verified:
                flash("Please verify your email before logging in.", "error")
                return render_template("auth/login.html"), 403
            try:
                session.permanent = True
                login_user(user, remember=bool(request.form.get("remember")))
                next_page = request.args.get("next")
                flash("Logged in successfully.", "success")
                if user.is_admin and request.form.get("admin_login"):
                    return redirect(url_for("admin.dashboard"))
                return redirect(next_page if _is_safe_next(next_page) else url_for("main.dashboard"))
            except Exception:
                logger.exception("Login session setup failed for email=%s", email)
                flash("Login could not be completed. Please try again.", "error")
                return render_template("auth/login.html"), 500

        flash("Invalid email or password.", "error")

    return render_template("auth/login.html")


@auth_bp.route("/verify-email/<token>")
def verify_email(token):
    token_hash = hash_token(token)
    user = User.query.filter_by(email_verification_token=token_hash).first()
    if not user:
        return _auth_response(
            "This verification link is invalid or has already been used.",
            "error",
            400,
            template="auth/login.html",
        )

    if user.is_email_verified:
        user.email_verification_token = None
        user.email_verification_expires_at = None
        db.session.commit()
        return _auth_response(
            "This email address has already been verified.",
            "info",
            200,
            template="auth/login.html",
        )

    if is_expired(user.email_verification_expires_at):
        return _auth_response(
            "This verification link has expired. Please register again or contact support.",
            "error",
            400,
            template="auth/login.html",
        )

    user.is_email_verified = True
    user.email_verification_token = None
    user.email_verification_expires_at = None
    db.session.commit()
    try:
        send_welcome_email(user)
    except Exception:
        logger.exception("Welcome email failed for user_id=%s", user.id)
    return _auth_response(
        "Email verified successfully. You can now log in.",
        "success",
        200,
        template="auth/login.html",
    )


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = (
            (request.get_json(silent=True) or {}).get("email")
            if request.is_json
            else request.form.get("email", "")
        )
        email = (email or "").strip().lower()
        if _rate_limited(_client_key("forgot", email), limit=5):
            return _auth_response(
                "If an account exists for that email, a password reset link has been sent.",
                "info",
                200,
                template="auth/forgot_password.html",
            )

        user = User.query.filter_by(email=email).first() if email else None
        if user:
            raw_token, token_hash = generate_token()
            user.password_reset_token = token_hash
            user.password_reset_expires_at = expires_in(
                current_app.config["PASSWORD_RESET_TOKEN_MINUTES"]
            )
            db.session.commit()
            try:
                send_password_reset_email(user, raw_token)
            except Exception:
                logger.exception("Password reset email failed for email=%s", email)

        return _auth_response(
            "If an account exists for that email, a password reset link has been sent.",
            "info",
            200,
            template="auth/forgot_password.html",
        )

    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    token_hash = hash_token(token)
    user = User.query.filter_by(password_reset_token=token_hash).first()

    if not user:
        return _auth_response(
            "This password reset link is invalid or has already been used.",
            "error",
            400,
            template="auth/reset_password.html",
            token=token,
        )

    if is_expired(user.password_reset_expires_at):
        user.password_reset_token = None
        user.password_reset_expires_at = None
        db.session.commit()
        return _auth_response(
            "This password reset link has expired. Please request a new one.",
            "error",
            400,
            template="auth/forgot_password.html",
        )

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        password = payload.get("password") if request.is_json else request.form.get("password", "")
        confirm = (
            payload.get("confirm_password")
            if request.is_json
            else request.form.get("confirm_password", "")
        )
        if not password or len(password) < 8:
            return _auth_response(
                "Password must be at least 8 characters.",
                "error",
                400,
                template="auth/reset_password.html",
                token=token,
            )
        if password != confirm:
            return _auth_response(
                "Passwords do not match.",
                "error",
                400,
                template="auth/reset_password.html",
                token=token,
            )

        user.password_hash = generate_password_hash(password)
        user.password_reset_token = None
        user.password_reset_expires_at = None
        user.is_email_verified = True
        db.session.commit()
        try:
            send_password_changed_email(
                user,
                _format_dt(utcnow()),
                ip_address=_client_ip(),
                user_agent=request.headers.get("User-Agent"),
            )
        except Exception:
            logger.exception("Password changed email failed for user_id=%s", user.id)
        return _auth_response(
            "Password reset successful. You can now log in.",
            "success",
            200,
            template="auth/login.html",
        )

    return render_template("auth/reset_password.html", token=token)


@auth_bp.route("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    payload = request.get_json(silent=True) or {}
    current_password = (
        payload.get("current_password")
        if request.is_json
        else request.form.get("current_password", "")
    )
    new_password = (
        payload.get("password") if request.is_json else request.form.get("password", "")
    )
    confirm = (
        payload.get("confirm_password")
        if request.is_json
        else request.form.get("confirm_password", "")
    )

    if not check_password_hash(current_user.password_hash, current_password or ""):
        return _auth_response("Current password is incorrect.", "error", 400)
    if not new_password or len(new_password) < 8:
        return _auth_response("Password must be at least 8 characters.", "error", 400)
    if new_password != confirm:
        return _auth_response("Passwords do not match.", "error", 400)

    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    try:
        send_password_changed_email(
            current_user,
            _format_dt(utcnow()),
            ip_address=_client_ip(),
            user_agent=request.headers.get("User-Agent"),
        )
    except Exception:
        logger.exception("Password changed email failed for user_id=%s", current_user.id)

    return _auth_response("Password changed successfully.", "success", 200)

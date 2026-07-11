import json
import logging
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required
from sqlalchemy import text

from app import db
from app.models import ActivityHistory, ScanResult
from app.services.history_service import MODULE_LABELS, module_label

main_bp = Blueprint("main", __name__)
logger = logging.getLogger("agroguide.main")


@main_bp.route("/")
def index():
    return render_template("landing.html")


@main_bp.route("/health")
def health():
    checks = {
        "app": "ok",
        "database": "unknown",
        "model_api_configured": bool(current_app.config.get("MODEL_API_URL")),
    }
    status_code = 200
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        db.session.rollback()
        logger.exception("Health check database probe failed.")
        checks["database"] = "error"
        status_code = 503
    return jsonify(checks), status_code


@main_bp.route("/dashboard")
@login_required
def dashboard():
    recent = (
        ActivityHistory.query.filter_by(user_id=current_user.id)
        .order_by(ActivityHistory.created_at.desc())
        .limit(12)
        .all()
    )
    total_scans = ScanResult.query.filter_by(user_id=current_user.id).count()
    total_activities = ActivityHistory.query.filter_by(user_id=current_user.id).count()

    quick_actions = [
        {"label": "Disease Detection", "url": url_for("detection.index"), "icon": "scan"},
        {"label": "Crop Recommendation", "url": url_for("crops.recommendation"), "icon": "sprout"},
        {"label": "Crop Suitability", "url": url_for("crops.suitability"), "icon": "check-circle"},
        {"label": "Cultivation Guide", "url": url_for("crops.guide"), "icon": "book-open"},
        {"label": "Weather", "url": url_for("weather.index"), "icon": "cloud-sun"},
        {"label": "Irrigation", "url": url_for("irrigation.index"), "icon": "droplets"},
        {"label": "Fertilizer", "url": url_for("fertilizer.index"), "icon": "flask-conical"},
        {"label": "Pest Help", "url": url_for("pest.index"), "icon": "bug"},
        {"label": "AI Assistant", "url": url_for("chatbot.index"), "icon": "message-circle"},
        {"label": "History", "url": url_for("main.history"), "icon": "history"},
    ]

    return render_template(
        "dashboard/index.html",
        recent_activities=recent,
        total_scans=total_scans,
        total_activities=total_activities,
        quick_actions=quick_actions,
        module_labels=MODULE_LABELS,
    )


@main_bp.route("/history", methods=["GET", "POST"])
@login_required
def history():
    if request.method == "POST" and request.form.get("action") == "delete":
        item_id = request.form.get("item_id", type=int)
        item = ActivityHistory.query.filter_by(
            id=item_id, user_id=current_user.id
        ).first()
        if item:
            try:
                db.session.delete(item)
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception("Failed to delete history item id=%s", item_id)
        return redirect(url_for("main.history", **{k: v for k, v in request.args.items()}))

    return render_template(
        "dashboard/history.html",
        items=_query_history(),
        modules=MODULE_LABELS,
        q=request.args.get("q", ""),
        module_filter=request.args.get("module", ""),
        date_from=request.args.get("date_from", ""),
        date_to=request.args.get("date_to", ""),
    )


def _query_history():
    q = ActivityHistory.query.filter_by(user_id=current_user.id)
    search = request.args.get("q", "").strip()
    module_f = request.args.get("module", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    if module_f:
        q = q.filter(ActivityHistory.module == module_f)
    if search:
        q = q.filter(ActivityHistory.title.ilike(f"%{search}%"))
    if date_from:
        try:
            d0 = datetime.strptime(date_from, "%Y-%m-%d")
            q = q.filter(ActivityHistory.created_at >= d0)
        except ValueError:
            pass
    if date_to:
        try:
            d1 = datetime.strptime(date_to, "%Y-%m-%d")
            q = q.filter(ActivityHistory.created_at <= d1.replace(hour=23, minute=59))
        except ValueError:
            pass

    items = q.order_by(ActivityHistory.created_at.desc()).limit(200).all()
    for item in items:
        try:
            item.summary_data = json.loads(item.summary or "{}")
        except json.JSONDecodeError:
            item.summary_data = {}
        item.module_label = module_label(item.module)
    return items


@main_bp.route("/uploads/<filename>")
@login_required
def serve_upload(filename):
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    scan = ScanResult.query.filter_by(image_filename=filename).first()
    if scan and (scan.user_id == current_user.id or current_user.is_admin):
        return send_from_directory(upload_dir, filename)
    abort(404)

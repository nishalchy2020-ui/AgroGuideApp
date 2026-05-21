import os
import requests

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import ScanResult
from app.services.history_service import log_activity
from app.services.knowledge_service import get_knowledge_for_class, severity_badge_class
from app.utils.helpers import humanize_class_name, save_upload

detection_bp = Blueprint("detection", __name__)


def is_remote_ai_ready():
    return bool(os.getenv("AI_API_URL"))


def predict_with_remote_api(file):
    ai_api_url = os.getenv("AI_API_URL")

    if not ai_api_url:
        return {
            "success": False,
            "error": "AI_API_URL is not configured."
        }

    file.stream.seek(0)

    response = requests.post(
        ai_api_url,
        files={
            "image": (
                file.filename,
                file.stream,
                file.content_type or "image/jpeg",
            )
        },
        timeout=60,
    )

    response.raise_for_status()
    return response.json()


@detection_bp.route("/")
@login_required
def index():
    model_ready = is_remote_ai_ready()
    return render_template("detection/index.html", model_ready=model_ready)


@detection_bp.route("/predict", methods=["POST"])
@login_required
def predict():
    if not is_remote_ai_ready():
        flash(
            "AI prediction API is not configured. Please set AI_API_URL in environment variables.",
            "error",
        )
        return redirect(url_for("detection.index"))

    file = request.files.get("image")

    if not file or not file.filename:
        flash("Please upload or capture an image.", "error")
        return redirect(url_for("detection.index"))

    try:
        filename, path = save_upload(file)

        # After saving, reset file stream and send same uploaded image to Render AI API
        result = predict_with_remote_api(file)

        if not result.get("success", True):
            flash(result.get("error", "Prediction failed from AI API."), "error")
            return redirect(url_for("detection.index"))

    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("detection.index"))
    except FileNotFoundError as e:
        flash(str(e), "error")
        return redirect(url_for("detection.index"))
    except requests.exceptions.RequestException as e:
        flash(f"AI API request failed: {e}", "error")
        return redirect(url_for("detection.index"))
    except Exception as e:
        flash(f"Prediction failed: {e}", "error")
        return redirect(url_for("detection.index"))

    class_name = (
        result.get("disease_class")
        or result.get("class_name")
        or result.get("prediction")
        or result.get("predicted_class")
    )

    if not class_name:
        flash("AI API did not return a disease class.", "error")
        return redirect(url_for("detection.index"))

    confidence = result.get("confidence", 0)

    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    knowledge = get_knowledge_for_class(class_name)
    label = humanize_class_name(class_name)
    severity = knowledge.get("severity", "medium")

    scan = ScanResult(
        user_id=current_user.id,
        image_filename=filename,
        disease_class=class_name,
        disease_label=label,
        confidence=confidence,
        severity=severity,
    )

    db.session.add(scan)
    db.session.flush()

    log_activity(
        current_user.id,
        "disease_scan",
        f"Disease scan: {label} ({confidence}%)",
        {
            "disease_class": class_name,
            "confidence": confidence,
            "severity": severity,
        },
        ref_id=scan.id,
    )

    db.session.commit()

    return render_template(
        "detection/result.html",
        scan=scan,
        knowledge=knowledge,
        badge_class=severity_badge_class(severity),
        image_url=url_for("main.serve_upload", filename=filename),
    )


@detection_bp.route("/result/<int:scan_id>")
@login_required
def result_detail(scan_id):
    scan = ScanResult.query.get_or_404(scan_id)

    if scan.user_id != current_user.id and not current_user.is_admin:
        flash("Access denied.", "error")
        return redirect(url_for("main.history"))

    knowledge = get_knowledge_for_class(scan.disease_class)

    return render_template(
        "detection/result.html",
        scan=scan,
        knowledge=knowledge,
        badge_class=severity_badge_class(scan.severity),
        image_url=url_for("main.serve_upload", filename=scan.image_filename),
    )
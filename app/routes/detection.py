import base64
import logging
import mimetypes

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import ScanResult
from app.services.history_service import log_activity
from app.services.knowledge_service import get_knowledge_for_class, severity_badge_class
from app.services.model_api_service import (
    ModelApiError,
    is_model_api_configured,
    predict_leaf_disease,
)
from app.utils.helpers import humanize_class_name, save_upload

detection_bp = Blueprint("detection", __name__)
logger = logging.getLogger("agroguide.detection")


def normalize_confidence_percent(value):
    """Return confidence as a display-ready percentage in the 0-100 range."""
    if isinstance(value, str):
        value = value.strip().rstrip("%")

    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0

    if confidence <= 1:
        confidence *= 100

    return max(0.0, min(confidence, 100.0))


def image_data_url(path):
    content_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


@detection_bp.route("/")
@login_required
def index():
    model_ready = is_model_api_configured()
    return render_template("detection/index.html", model_ready=model_ready)


@detection_bp.route("/predict", methods=["POST"])
@login_required
def predict():
    if not is_model_api_configured():
        flash(
            "AI prediction is not configured. Set MODEL_API_URL in environment variables.",
            "error",
        )
        return redirect(url_for("detection.index"))

    file = request.files.get("image")

    if not file or not file.filename:
        flash("Please upload or capture an image.", "error")
        return redirect(url_for("detection.index"))

    try:
        filename, path = save_upload(file)
        result = predict_leaf_disease(
            path,
            filename=file.filename,
            content_type=file.content_type or "image/jpeg",
        )

    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("detection.index"))
    except FileNotFoundError as e:
        flash(str(e), "error")
        return redirect(url_for("detection.index"))
    except ModelApiError as e:
        logger.warning("AWS model prediction failed: %s", e)
        flash(str(e), "error")
        return redirect(url_for("detection.index"))
    except Exception as e:
        db.session.rollback()
        logger.exception("Prediction failed.")
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

    confidence = normalize_confidence_percent(
        result.get("confidence_percent", result.get("confidence", 0))
    )

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
            "model_api": result.get("additional_info", {}),
        },
        ref_id=scan.id,
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Failed to save scan result for user_id=%s", current_user.id)
        flash("Prediction succeeded, but saving the result failed. Please try again.", "error")
        return redirect(url_for("detection.index"))

    return render_template(
        "detection/result.html",
        scan=scan,
        knowledge=knowledge,
        badge_class=severity_badge_class(severity),
        confidence_percent=normalize_confidence_percent(scan.confidence),
        api_result=result.get("raw_response", {}),
        additional_info=result.get("additional_info", {}),
        image_src=image_data_url(path),
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
        confidence_percent=normalize_confidence_percent(scan.confidence),
        api_result={},
        additional_info={},
        image_src=None,
        image_url=url_for("main.serve_upload", filename=scan.image_filename),
    )

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app import db
from app.models import ScanResult
from app.services import model_service
from app.services.history_service import log_activity
from app.services.knowledge_service import get_knowledge_for_class, severity_badge_class
from app.utils.helpers import humanize_class_name, save_upload

detection_bp = Blueprint("detection", __name__)


@detection_bp.route("/")
@login_required
def index():
    model_ready = model_service.is_model_ready()
    return render_template("detection/index.html", model_ready=model_ready)


@detection_bp.route("/predict", methods=["POST"])
@login_required
def predict():
    if not model_service.is_model_ready():
        flash(
            "Model files missing. Add plant_disease_checkpoint.pth and class_indices.json to app/ml_models/.",
            "error",
        )
        return redirect(url_for("detection.index"))

    file = request.files.get("image")
    if not file or not file.filename:
        flash("Please upload or capture an image.", "error")
        return redirect(url_for("detection.index"))

    try:
        filename, path = save_upload(file)
        result = model_service.predict(path)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("detection.index"))
    except FileNotFoundError as e:
        flash(str(e), "error")
        return redirect(url_for("detection.index"))
    except Exception as e:
        flash(f"Prediction failed: {e}", "error")
        return redirect(url_for("detection.index"))

    class_name = result["class_name"]
    knowledge = get_knowledge_for_class(class_name)
    label = humanize_class_name(class_name)
    severity = knowledge.get("severity", "medium")

    scan = ScanResult(
        user_id=current_user.id,
        image_filename=filename,
        disease_class=class_name,
        disease_label=label,
        confidence=result["confidence"],
        severity=severity,
    )
    db.session.add(scan)
    db.session.flush()
    log_activity(
        current_user.id,
        "disease_scan",
        f"Disease scan: {label} ({result['confidence_percent']}%)",
        {
            "disease_class": class_name,
            "confidence": result["confidence"],
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

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

SUPPORTED_DETECTIONS = {
    "Apple___Apple_scab": "Apple Scab",
    "Apple___Black_rot": "Apple Black Rot",
    "Apple___Cedar_apple_rust": "Apple Cedar Rust",
    "Apple___healthy": "Healthy Apple",
    "Blueberry___healthy": "Healthy Blueberry",
    "Cherry_(including_sour)___healthy": "Healthy Cherry",
    "Cherry_(including_sour)___Powdery_mildew": "Cherry Powdery Mildew",
    "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": "Corn Gray Leaf Spot",
    "Corn_(maize)___Common_rust_": "Corn Common Rust",
    "Corn_(maize)___healthy": "Healthy Corn",
    "Corn_(maize)___Northern_Leaf_Blight": "Corn Northern Leaf Blight",
    "Grape___Black_rot": "Grape Black Rot",
    "Grape___Esca_(Black_Measles)": "Grape Esca (Black Measles)",
    "Grape___healthy": "Healthy Grape",
    "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": "Grape Leaf Blight",
    "Orange___Haunglongbing_(Citrus_greening)": "Citrus Greening (HLB)",
    "Peach___Bacterial_spot": "Peach Bacterial Spot",
    "Peach___healthy": "Healthy Peach",
    "Pepper,_bell___Bacterial_spot": "Bell Pepper Bacterial Spot",
    "Pepper,_bell___healthy": "Healthy Bell Pepper",
    "Potato___Early_blight": "Potato Early Blight",
    "Potato___healthy": "Healthy Potato",
    "Potato___Late_blight": "Potato Late Blight",
    "Raspberry___healthy": "Healthy Raspberry",
    "Soybean___healthy": "Healthy Soybean",
    "Squash___Powdery_mildew": "Squash Powdery Mildew",
    "Strawberry___healthy": "Healthy Strawberry",
    "Strawberry___Leaf_scorch": "Strawberry Leaf Scorch",
    "Tomato___Bacterial_spot": "Tomato Bacterial Spot",
    "Tomato___Early_blight": "Tomato Early Blight",
    "Tomato___healthy": "Healthy Tomato",
    "Tomato___Late_blight": "Tomato Late Blight",
    "Tomato___Leaf_Mold": "Tomato Leaf Mold",
    "Tomato___Septoria_leaf_spot": "Tomato Septoria Leaf Spot",
    "Tomato___Spider_mites Two-spotted_spider_mite": "Tomato Spider Mites",
    "Tomato___Target_Spot": "Tomato Target Spot",
    "Tomato___Tomato_mosaic_virus": "Tomato Mosaic Virus",
    "Tomato___Tomato_Yellow_Leaf_Curl_Virus": "Tomato Yellow Leaf Curl Virus",
}

SUPPORTED_DETECTION_DESCRIPTIONS = {
    "Apple___Apple_scab": "A fungal apple disease that often causes dark, scabby spots on leaves and fruit.",
    "Apple___Black_rot": "A fungal disease that can create leaf spots, fruit rot, and branch cankers on apple trees.",
    "Apple___Cedar_apple_rust": "A rust disease linked to apple and cedar hosts, often seen as orange-yellow leaf spots.",
    "Apple___healthy": "Apple foliage with no strong visible symptoms from the trained disease classes.",
    "Blueberry___healthy": "Blueberry foliage that appears healthy within the model's supported visual classes.",
    "Cherry_(including_sour)___healthy": "Cherry foliage with no strong visible disease pattern from the trained classes.",
    "Cherry_(including_sour)___Powdery_mildew": "A fungal disease that can leave pale, powdery growth on cherry leaves and shoots.",
    "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": "A corn leaf disease that usually forms rectangular gray or tan lesions between veins.",
    "Corn_(maize)___Common_rust_": "A corn disease marked by small rust-colored pustules scattered across leaf surfaces.",
    "Corn_(maize)___healthy": "Corn foliage that appears healthy within the model's supported visual classes.",
    "Corn_(maize)___Northern_Leaf_Blight": "A corn disease that often forms long, cigar-shaped gray-green lesions on leaves.",
    "Grape___Black_rot": "A fungal grape disease that can cause brown leaf spots and shriveled dark fruit.",
    "Grape___Esca_(Black_Measles)": "A grapevine disease often associated with striped leaf discoloration and dark fruit spotting.",
    "Grape___healthy": "Grape foliage with no strong visible disease pattern from the trained classes.",
    "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": "A grape leaf disease that commonly creates angular brown spots and leaf blight symptoms.",
    "Orange___Haunglongbing_(Citrus_greening)": "A serious citrus disease linked with blotchy yellowing, weak growth, and poor fruit quality.",
    "Peach___Bacterial_spot": "A bacterial disease that can create small dark leaf spots and shot-hole damage on peach leaves.",
    "Peach___healthy": "Peach foliage that appears healthy within the model's supported visual classes.",
    "Pepper,_bell___Bacterial_spot": "A bacterial bell pepper disease that causes small water-soaked or dark leaf spots.",
    "Pepper,_bell___healthy": "Bell pepper foliage with no strong visible disease pattern from the trained classes.",
    "Potato___Early_blight": "A potato disease often recognized by brown leaf spots with target-like rings.",
    "Potato___healthy": "Potato foliage that appears healthy within the model's supported visual classes.",
    "Potato___Late_blight": "A fast-moving potato disease that can create dark, water-soaked lesions on leaves.",
    "Raspberry___healthy": "Raspberry foliage with no strong visible disease pattern from the trained classes.",
    "Soybean___healthy": "Soybean foliage that appears healthy within the model's supported visual classes.",
    "Squash___Powdery_mildew": "A fungal squash disease that creates white powdery patches on leaf surfaces.",
    "Strawberry___healthy": "Strawberry foliage with no strong visible disease pattern from the trained classes.",
    "Strawberry___Leaf_scorch": "A strawberry disease that can create reddish-purple spots and scorched-looking leaf edges.",
    "Tomato___Bacterial_spot": "A bacterial tomato disease that often causes small dark spots on leaves and fruit.",
    "Tomato___Early_blight": "A tomato disease commonly seen as brown leaf spots with concentric rings.",
    "Tomato___healthy": "Tomato foliage that appears healthy within the model's supported visual classes.",
    "Tomato___Late_blight": "A destructive tomato disease that can form dark, water-soaked leaf and stem lesions.",
    "Tomato___Leaf_Mold": "A tomato disease favored by humidity, often showing yellow leaf patches and mold underneath.",
    "Tomato___Septoria_leaf_spot": "A tomato leaf spot disease that produces many small circular spots with pale centers.",
    "Tomato___Spider_mites Two-spotted_spider_mite": "A mite-related tomato issue that can cause stippling, yellowing, and bronzed leaves.",
    "Tomato___Target_Spot": "A tomato disease that creates round target-like leaf lesions and can weaken foliage.",
    "Tomato___Tomato_mosaic_virus": "A viral tomato disease that can cause mottled leaves, curling, and uneven growth.",
    "Tomato___Tomato_Yellow_Leaf_Curl_Virus": "A viral tomato disease often linked with yellowing, curled leaves, and stunted plants.",
}


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


@detection_bp.route("/supported-detections")
@login_required
def supported_detections():
    grouped = {}
    for class_key, label in SUPPORTED_DETECTIONS.items():
        plant = label
        for prefix in ("Healthy ", "Bell Pepper ", "Citrus "):
            if plant.startswith(prefix):
                plant = plant[len(prefix):]
        plant = plant.split(" ", 1)[0]
        if label.startswith("Bell Pepper"):
            plant = "Bell Pepper"
        elif label.startswith("Citrus"):
            plant = "Citrus"
        grouped.setdefault(plant, []).append(
            {
                "class_key": class_key,
                "label": label,
                "description": SUPPORTED_DETECTION_DESCRIPTIONS[class_key],
            }
        )

    return render_template(
        "detection/supported.html",
        grouped_detections=dict(sorted(grouped.items())),
        total_detections=len(SUPPORTED_DETECTIONS),
    )


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

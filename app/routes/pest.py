from flask import Blueprint, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.services import farming_rules
from app.services.history_service import log_activity

pest_bp = Blueprint("pest", __name__)


@pest_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    result = None
    crops = farming_rules.list_crops()
    if request.method == "POST":
        result = farming_rules.pest_disease_help(
            crop_name=request.form.get("crop_name", ""),
            symptom=request.form.get("symptom", ""),
        )
        log_activity(
            current_user.id,
            "pest_help",
            f"Pest help: {result['crop_name']} — {result['possible_issue']}",
            result,
        )
        db.session.commit()

    return render_template(
        "pest/index.html",
        result=result,
        crops=crops,
        symptoms=farming_rules.SYMPTOMS,
        detection_url=url_for("detection.index"),
    )

import logging

from flask import Blueprint, flash, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.services import farming_rules
from app.services.history_service import log_activity

pest_bp = Blueprint("pest", __name__)
logger = logging.getLogger("agroguide.pest")


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
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Failed to save pest help history.")
            flash("Pest guidance was generated, but history could not be saved.", "warning")

    return render_template(
        "pest/index.html",
        result=result,
        crops=crops,
        symptoms=farming_rules.SYMPTOMS,
        detection_url=url_for("detection.index"),
    )

import logging

from flask import Blueprint, flash, render_template, request
from flask_login import current_user, login_required

from app import db
from app.services import farming_rules
from app.services.history_service import log_activity
from app.services.user_context import recent_disease_context

fertilizer_bp = Blueprint("fertilizer", __name__)
logger = logging.getLogger("agroguide.fertilizer")


@fertilizer_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    result = None
    crops = farming_rules.list_crops()
    if request.method == "POST":
        result = farming_rules.fertilizer_advice(
            crop_name=request.form.get("crop_name", ""),
            growth_stage=request.form.get("growth_stage", ""),
            soil_type=request.form.get("soil_type", ""),
            n=request.form.get("nitrogen") or None,
            p=request.form.get("phosphorus") or None,
            k=request.form.get("potassium") or None,
            ph=request.form.get("ph") or None,
            history_context=recent_disease_context(current_user.id),
        )
        if "error" not in result:
            log_activity(
                current_user.id,
                "fertilizer",
                f"Fertilizer: {result['crop_name']} — {request.form.get('growth_stage', '')}",
                result,
            )
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception("Failed to save fertilizer history.")
                flash("Fertilizer advice was generated, but history could not be saved.", "warning")

    return render_template(
        "fertilizer/index.html",
        result=result,
        crops=crops,
        soils=farming_rules.SOIL_TYPES,
        stages=farming_rules.GROWTH_STAGES,
    )

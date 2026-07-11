import logging

from flask import Blueprint, flash, render_template, request
from flask_login import current_user, login_required

from app import db
from app.services import farming_rules
from app.services.history_service import log_activity
from app.services.user_context import recent_disease_context

irrigation_bp = Blueprint("irrigation", __name__)
logger = logging.getLogger("agroguide.irrigation")


@irrigation_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    result = None
    crops = farming_rules.list_crops()
    if request.method == "POST":
        result = farming_rules.irrigation_advice(
            crop_name=request.form.get("crop_name", ""),
            growth_stage=request.form.get("growth_stage", ""),
            soil_type=request.form.get("soil_type", ""),
            rainfall=request.form.get("rainfall") or None,
            history_context=recent_disease_context(current_user.id),
        )
        if "error" not in result:
            log_activity(
                current_user.id,
                "irrigation",
                f"Irrigation: {result['crop_name']} ({request.form.get('growth_stage', '')})",
                result,
            )
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception("Failed to save irrigation history.")
                flash("Irrigation advice was generated, but history could not be saved.", "warning")

    return render_template(
        "irrigation/index.html",
        result=result,
        crops=crops,
        soils=farming_rules.SOIL_TYPES,
        stages=farming_rules.GROWTH_STAGES,
    )

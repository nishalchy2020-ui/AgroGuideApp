from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from app import db
from app.services import farming_rules
from app.services.history_service import log_activity

irrigation_bp = Blueprint("irrigation", __name__)


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
        )
        if "error" not in result:
            log_activity(
                current_user.id,
                "irrigation",
                f"Irrigation: {result['crop_name']} ({request.form.get('growth_stage', '')})",
                result,
            )
            db.session.commit()

    return render_template(
        "irrigation/index.html",
        result=result,
        crops=crops,
        soils=farming_rules.SOIL_TYPES,
        stages=farming_rules.GROWTH_STAGES,
    )

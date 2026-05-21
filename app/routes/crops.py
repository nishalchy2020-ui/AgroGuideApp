from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from app import db
from app.services import farming_rules
from app.services.history_service import log_activity

crops_bp = Blueprint("crops", __name__)


@crops_bp.route("/recommendation", methods=["GET", "POST"])
@login_required
def recommendation():
    result = None
    if request.method == "POST":
        result = farming_rules.recommend_crops(
            soil_type=request.form.get("soil_type", ""),
            season=request.form.get("season", ""),
            water_availability=request.form.get("water_availability", ""),
            temperature=request.form.get("temperature"),
            rainfall=request.form.get("rainfall") or None,
            humidity=request.form.get("humidity") or None,
        )
        top = result["recommendations"][0]["crop_name"] if result["recommendations"] else "Analysis"
        log_activity(
            current_user.id,
            "crop_recommendation",
            f"Crop recommendation: {top}",
            result,
        )
        db.session.commit()

    return render_template(
        "crops/recommendation.html",
        result=result,
        soils=farming_rules.SOIL_TYPES,
        seasons=farming_rules.SEASONS,
        water_levels=farming_rules.WATER_LEVELS,
    )


@crops_bp.route("/suitability", methods=["GET", "POST"])
@login_required
def suitability():
    result = None
    crops = farming_rules.list_crops()
    if request.method == "POST":
        result = farming_rules.check_suitability(
            crop_name=request.form.get("crop_name", ""),
            soil_type=request.form.get("soil_type", ""),
            season=request.form.get("season", ""),
            water_availability=request.form.get("water_availability", ""),
            temperature=request.form.get("temperature") or None,
            humidity=request.form.get("humidity") or None,
            location=request.form.get("location", ""),
        )
        log_activity(
            current_user.id,
            "crop_suitability",
            f"Suitability: {result.get('crop_name', 'Crop')} — {result.get('label', '')}",
            result,
        )
        db.session.commit()

    return render_template(
        "crops/suitability.html",
        result=result,
        crops=crops,
        soils=farming_rules.SOIL_TYPES,
        seasons=farming_rules.SEASONS,
        water_levels=farming_rules.WATER_LEVELS,
    )


@crops_bp.route("/guide", methods=["GET", "POST"])
@login_required
def guide():
    crops = farming_rules.list_crops()
    guide_data = None
    crop_sel = request.form.get("crop_name") or request.args.get("crop", "")
    if crop_sel:
        guide_data = farming_rules.get_cultivation_guide(crop_sel)
        if guide_data and request.method == "POST":
            log_activity(
                current_user.id,
                "cultivation_guide",
                f"Guide: {guide_data['crop_name']}",
                {"crop_key": guide_data["crop_key"]},
            )
            db.session.commit()

    return render_template("crops/guide.html", crops=crops, guide=guide_data, crop_sel=crop_sel)

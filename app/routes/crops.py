import logging

from flask import Blueprint, flash, render_template, request
from flask_login import current_user, login_required

from app import db
from app.services import farming_rules
from app.services.history_service import log_activity
from app.services.user_context import recent_disease_context

crops_bp = Blueprint("crops", __name__)
logger = logging.getLogger("agroguide.crops")


@crops_bp.route("/recommendation", methods=["GET", "POST"])
@login_required
def recommendation():
    result = None
    if request.method == "POST":
        history_context = recent_disease_context(current_user.id)
        result = farming_rules.recommend_crops(
            soil_type=request.form.get("soil_type", ""),
            season=request.form.get("season", ""),
            water_availability=request.form.get("water_availability", ""),
            temperature=request.form.get("temperature"),
            rainfall=request.form.get("rainfall") or None,
            humidity=request.form.get("humidity") or None,
            region=request.form.get("region", ""),
            history_context=history_context,
        )
        top = result["recommendations"][0]["crop_name"] if result["recommendations"] else "Analysis"
        log_activity(
            current_user.id,
            "crop_recommendation",
            f"Crop recommendation: {top}",
            result,
        )
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Failed to save crop recommendation history.")
            flash("Recommendation was generated, but history could not be saved.", "warning")

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
        history_context = recent_disease_context(current_user.id)
        result = farming_rules.check_suitability(
            crop_name=request.form.get("crop_name", ""),
            soil_type=request.form.get("soil_type", ""),
            season=request.form.get("season", ""),
            water_availability=request.form.get("water_availability", ""),
            temperature=request.form.get("temperature") or None,
            humidity=request.form.get("humidity") or None,
            location=request.form.get("location", ""),
            history_context=history_context,
        )
        log_activity(
            current_user.id,
            "crop_suitability",
            f"Suitability: {result.get('crop_name', 'Crop')} — {result.get('label', '')}",
            result,
        )
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Failed to save crop suitability history.")
            flash("Suitability was generated, but history could not be saved.", "warning")

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
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception("Failed to save cultivation guide history.")
                flash("Guide was loaded, but history could not be saved.", "warning")

    return render_template("crops/guide.html", crops=crops, guide=guide_data, crop_sel=crop_sel)

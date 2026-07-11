import logging

from flask import Blueprint, flash, render_template, request
from flask_login import current_user, login_required

from app import db
from app.models import WeatherSearch
from app.services import weather_service
from app.services.history_service import log_activity

weather_bp = Blueprint("weather", __name__)
logger = logging.getLogger("agroguide.weather")


@weather_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    weather_data = None
    location = None
    advice = None
    risk = None

    if request.method == "POST":
        query = request.form.get("location", "").strip()
        if not query:
            flash("Enter a city or location name.", "error")
        else:
            try:
                results = weather_service.geocode_location(query)
                if not results:
                    flash("Location not found. Try another spelling.", "error")
                else:
                    loc = results[0]
                    weather_data = weather_service.fetch_weather(
                        loc["latitude"], loc["longitude"]
                    )
                    current = weather_data.get("current", {})
                    temp = current.get("temperature_2m")
                    humidity = current.get("relative_humidity_2m")
                    wind = current.get("wind_speed_10m")
                    rainfall = current.get("precipitation", 0)

                    advice = weather_service.generate_farming_advice(
                        temp, humidity, wind, rainfall
                    )
                    risk = weather_service.generate_disease_risk(
                        temp, humidity, rainfall
                    )

                    location = {
                        "name": loc.get("name", query),
                        "country": loc.get("country", ""),
                        "latitude": loc["latitude"],
                        "longitude": loc["longitude"],
                    }

                    record = WeatherSearch(
                        user_id=current_user.id,
                        location_name=f"{location['name']}, {location['country']}".strip(", "),
                        latitude=loc["latitude"],
                        longitude=loc["longitude"],
                        temperature=temp,
                        humidity=humidity,
                        wind_speed=wind,
                        rainfall=rainfall,
                        farming_advice=advice,
                        disease_risk=risk["message"],
                    )
                    db.session.add(record)
                    db.session.flush()
                    log_activity(
                        current_user.id,
                        "weather",
                        f"Weather: {record.location_name}",
                        {
                            "temperature": temp,
                            "humidity": humidity,
                            "advice": advice,
                            "risk": risk,
                        },
                        ref_id=record.id,
                    )
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                        logger.exception("Failed to save weather history for user_id=%s", current_user.id)
                        flash("Weather loaded, but history could not be saved.", "warning")
            except Exception as e:
                db.session.rollback()
                logger.exception("Weather request failed for query=%s", query)
                flash(f"Weather service error: {e}", "error")

    history = (
        WeatherSearch.query.filter_by(user_id=current_user.id)
        .order_by(WeatherSearch.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "weather/index.html",
        weather_data=weather_data,
        location=location,
        advice=advice,
        risk=risk,
        history=history,
    )

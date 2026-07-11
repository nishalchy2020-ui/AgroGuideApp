from collections import Counter

from app.models import ActivityHistory, ScanResult, WeatherSearch
from app.services.history_service import module_label
from app.utils.helpers import humanize_class_name


def recent_disease_context(user_id, limit=8):
    scans = (
        ScanResult.query.filter_by(user_id=user_id)
        .order_by(ScanResult.created_at.desc())
        .limit(limit)
        .all()
    )
    if not scans:
        return {
            "has_history": False,
            "recent_diseases": [],
            "crops": [],
            "risk_note": "",
        }

    classes = [scan.disease_class for scan in scans]
    crops = [_crop_from_class(name) for name in classes]
    disease_counts = Counter(classes)
    crop_counts = Counter(crop for crop in crops if crop)
    top_disease = disease_counts.most_common(1)[0][0]
    top_crop = crop_counts.most_common(1)[0][0] if crop_counts else None

    note = f"Recent scan history shows {humanize_class_name(top_disease)}"
    if top_crop:
        note += f" pressure in {top_crop.title()}."
    else:
        note += "."

    return {
        "has_history": True,
        "recent_diseases": classes,
        "crops": sorted(set(crop for crop in crops if crop)),
        "top_disease": top_disease,
        "top_crop": top_crop,
        "risk_note": note,
    }


def _crop_from_class(class_name):
    text = (class_name or "").replace("___", "_").replace("__", "_")
    if not text:
        return ""
    return text.split("_", 1)[0].lower()


def chatbot_user_context(user_id):
    disease_context = recent_disease_context(user_id)
    weather = (
        WeatherSearch.query.filter_by(user_id=user_id)
        .order_by(WeatherSearch.created_at.desc())
        .first()
    )
    activities = (
        ActivityHistory.query.filter_by(user_id=user_id)
        .order_by(ActivityHistory.created_at.desc())
        .limit(5)
        .all()
    )

    activity_titles = [
        f"{module_label(item.module)}: {item.title}" for item in activities
    ]
    latest_weather = None
    if weather:
        latest_weather = {
            "location": weather.location_name,
            "temperature": weather.temperature,
            "humidity": weather.humidity,
            "rainfall": weather.rainfall,
            "disease_risk": weather.disease_risk,
        }

    return {
        "disease": disease_context,
        "weather": latest_weather,
        "recent_activity": activity_titles,
        "summary": _context_summary(disease_context, latest_weather, activity_titles),
    }


def _context_summary(disease_context, weather, activity_titles):
    parts = []
    if disease_context.get("has_history"):
        parts.append(disease_context["risk_note"])
    if weather:
        weather_bits = [f"last weather search was {weather['location']}"]
        if weather.get("temperature") is not None:
            weather_bits.append(f"{weather['temperature']}C")
        if weather.get("humidity") is not None:
            weather_bits.append(f"{weather['humidity']}% humidity")
        if weather.get("rainfall") is not None:
            weather_bits.append(f"{weather['rainfall']}mm rainfall")
        parts.append(", ".join(weather_bits) + ".")
    if activity_titles:
        parts.append("Recent AgroGuide activity: " + "; ".join(activity_titles[:3]) + ".")
    return " ".join(parts)

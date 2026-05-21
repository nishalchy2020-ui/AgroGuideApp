import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_MODEL_PATH = _DATA_DIR / "crop_model.json"
_GUIDES_PATH = _DATA_DIR / "crop_guides.json"


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _norm(text):
    return (text or "").strip().lower()


def _to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _range_score(value, expected_range, margin):
    if value is None:
        return 0.65, "No numeric value supplied; using moderate confidence."

    low, high = expected_range
    if low <= value <= high:
        return 1.0, f"{value:g} is inside the preferred range ({low}-{high})."

    if value < low:
        distance = low - value
        direction = "below"
    else:
        distance = value - high
        direction = "above"

    score = max(0.0, 1.0 - (distance / margin))
    return score, f"{value:g} is {direction} the preferred range ({low}-{high})."


def _contains_any(value, terms):
    value_l = _norm(value)
    return any(term in value_l or value_l in term for term in terms if value_l)


def _categorical_score(value, terms):
    if not value:
        return 0.5
    return 1.0 if _contains_any(value, terms) else 0.2


def _water_score(input_water, expected_water, encoding):
    given = encoding.get(_norm(input_water), 0.5)
    expected = encoding.get(_norm(expected_water), 0.5)
    return max(0.0, 1.0 - abs(given - expected))


def _humidity_score(humidity, humidity_max):
    h = _to_float(humidity)
    if h is None:
        return 0.75, None
    if h <= humidity_max:
        return 1.0, f"Humidity ({h:g}%) is below the disease-risk threshold."
    penalty = min(1.0, (h - humidity_max) / 20)
    return max(0.0, 1.0 - penalty), f"Humidity ({h:g}%) raises disease pressure."


def _tips_for_crop(guide):
    return [
        tip
        for tip in (
            guide.get("sowing", ""),
            guide.get("irrigation", ""),
            guide.get("pest_care", ""),
        )
        if tip
    ]


def recommend_crops(
    soil_type,
    season,
    water_availability,
    temperature,
    rainfall=None,
    humidity=None,
):
    model = _load_json(_MODEL_PATH)
    guides = _load_json(_GUIDES_PATH)
    weights = model["feature_weights"]
    water_encoding = model["water_encoding"]
    temp = _to_float(temperature)
    rain = _to_float(rainfall)

    recommendations = []
    for crop_key, features in model["crops"].items():
        guide = guides.get(crop_key, {})
        soil_score = _categorical_score(soil_type, features["soil_terms"])
        season_score = _categorical_score(season, features["season_terms"])
        water_score = _water_score(
            water_availability, features["water"], water_encoding
        )
        temp_score, temp_reason = _range_score(
            temp, features["temperature_c"], margin=12
        )
        rain_score, rain_reason = _range_score(
            rain, features["rainfall_mm"], margin=700
        )
        humidity_score, humidity_reason = _humidity_score(
            humidity, features.get("humidity_max", 85)
        )

        weighted_score = (
            soil_score * weights["soil"]
            + season_score * weights["season"]
            + water_score * weights["water"]
            + temp_score * weights["temperature"]
            + rain_score * weights["rainfall"]
            + humidity_score * weights["humidity"]
        )

        reasons = []
        if soil_score >= 1:
            reasons.append(f"Soil type matches {guide.get('name', crop_key)} preferences.")
        else:
            reasons.append(
                "Soil match is weaker; organic matter or drainage correction may help."
            )

        if season_score >= 1:
            reasons.append("Season aligns with the crop planting window.")
        else:
            reasons.append("Season is outside the strongest model fit.")

        if water_score >= 0.85:
            reasons.append("Water availability matches expected crop demand.")
        else:
            reasons.append("Water availability differs from the crop's typical need.")

        reasons.append(temp_reason.replace("preferred", "temperature"))
        if rainfall is not None:
            reasons.append(rain_reason.replace("preferred", "rainfall"))
        if humidity_reason:
            reasons.append(humidity_reason)

        recommendations.append(
            {
                "crop_key": crop_key,
                "crop_name": guide.get("name", crop_key.title()),
                "score": round(weighted_score * 100, 1),
                "reasons": reasons,
                "tips": _tips_for_crop(guide),
                "model": model["model_name"],
            }
        )

    recommendations.sort(key=lambda item: item["score"], reverse=True)
    return {
        "recommendations": recommendations[:5],
        "inputs": {
            "soil_type": soil_type,
            "season": season,
            "water_availability": water_availability,
            "temperature": temperature,
            "rainfall": rainfall,
            "humidity": humidity,
        },
        "model": model["model_name"],
    }

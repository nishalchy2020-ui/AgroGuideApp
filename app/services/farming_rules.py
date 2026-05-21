import json
import logging
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data" / "crop_guides.json"
_logger = logging.getLogger("agroguide")

SOIL_TYPES = ["loam", "sandy loam", "clay", "clay loam", "sandy", "silt", "peat", "chalky"]
SEASONS = ["spring", "summer", "autumn", "winter", "monsoon", "wet season", "cool season", "dry season"]
WATER_LEVELS = ["low", "medium", "high"]
GROWTH_STAGES = ["seedling", "vegetative", "flowering", "fruiting", "maturity", "harvest"]
SYMPTOMS = [
    "yellow leaves", "brown spots", "wilting", "holes in leaves", "white powder",
    "curling leaves", "stunted growth", "root rot smell", "chewed leaves", "mosaic pattern",
]


def _load_guides():
    with open(_DATA, encoding="utf-8") as f:
        return json.load(f)


def list_crops():
    guides = _load_guides()
    return sorted((v["name"], k) for k, v in guides.items())


def _norm_crop(crop):
    return (crop or "").strip().lower().replace(" ", "_").replace("-", "_")


def _score_crop(guide, soil, season, water, temp, rainfall=None, humidity=None):
    score = 50.0
    reasons = []

    soil_l = (soil or "").lower()
    if any(s in soil_l for s in guide.get("soils", [])):
        score += 15
        reasons.append(f"Soil type ({soil}) matches {guide['name']} preferences.")
    else:
        score -= 10
        reasons.append(f"Soil may need amendment for {guide['name']}.")

    season_l = (season or "").lower()
    if any(s in season_l for s in guide.get("seasons", [])) or season_l in ("", "all"):
        score += 15
        reasons.append(f"Season ({season}) is suitable for planting window.")
    else:
        score -= 8
        reasons.append(f"Season ({season}) is outside ideal planting period.")

    water_need = guide.get("water", "medium")
    water_l = (water or "medium").lower()
    water_map = {"low": 0, "medium": 1, "high": 2}
    diff = abs(water_map.get(water_l, 1) - water_map.get(water_need, 1))
    if diff == 0:
        score += 12
        reasons.append("Water availability aligns with crop needs.")
    elif diff == 1:
        score += 4
        reasons.append("Water availability is acceptable with management.")
    else:
        score -= 12
        reasons.append("Water availability may be insufficient or excessive.")

    tmin, tmax = guide.get("temp_range", [15, 30])
    if temp is not None:
        try:
            t = float(temp)
            if tmin <= t <= tmax:
                score += 15
                reasons.append(f"Temperature ({t}C) is in optimal range ({tmin}-{tmax}C).")
            elif tmin - 5 <= t <= tmax + 5:
                score += 5
                reasons.append(f"Temperature ({t}C) is marginal; use season extension or shade.")
            else:
                score -= 15
                reasons.append(f"Temperature ({t}C) is outside ideal range ({tmin}-{tmax}C).")
        except ValueError:
            pass

    if rainfall is not None:
        try:
            r = float(rainfall)
            rmin, rmax = guide.get("rainfall_mm", [300, 1000])
            if rmin <= r <= rmax:
                score += 8
                reasons.append("Rainfall fits expected annual needs.")
            elif r < rmin:
                score -= 5
                reasons.append("Rainfall may be low; plan supplemental irrigation.")
            else:
                score -= 3
                reasons.append("High rainfall; ensure drainage and disease scouting.")
        except ValueError:
            pass

    if humidity is not None:
        try:
            h = float(humidity)
            if h > 85:
                score -= 5
                reasons.append("High humidity increases fungal disease risk.")
        except ValueError:
            pass

    score = max(0, min(100, score))
    return score, reasons


def recommend_crops(soil_type, season, water_availability, temperature, rainfall=None, humidity=None):
    try:
        from app.services.crop_model import recommend_crops as model_recommend_crops

        return model_recommend_crops(
            soil_type,
            season,
            water_availability,
            temperature,
            rainfall=rainfall,
            humidity=humidity,
        )
    except Exception:
        _logger.exception("Local crop model failed; falling back to rule scorer.")

    guides = _load_guides()
    results = []
    for key, guide in guides.items():
        score, reasons = _score_crop(
            guide, soil_type, season, water_availability, temperature, rainfall, humidity
        )
        tips = [
            guide.get("sowing", ""),
            guide.get("irrigation", ""),
            guide.get("pest_care", ""),
        ]
        results.append({
            "crop_key": key,
            "crop_name": guide["name"],
            "score": round(score, 1),
            "reasons": reasons,
            "tips": [t for t in tips if t],
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:5]
    return {
        "recommendations": top,
        "inputs": {
            "soil_type": soil_type,
            "season": season,
            "water_availability": water_availability,
            "temperature": temperature,
            "rainfall": rainfall,
            "humidity": humidity,
        },
    }


def check_suitability(crop_name, soil_type, season, water_availability, temperature=None, humidity=None, location=None):
    guides = _load_guides()
    key = _norm_crop(crop_name)
    if key not in guides:
        for k, g in guides.items():
            if crop_name and crop_name.lower() in g["name"].lower():
                key = k
                break
    if key not in guides:
        return {
            "status": "unknown",
            "label": "Crop not found",
            "score": 0,
            "explanation": f"No guide data for '{crop_name}'. Try: tomato, potato, corn, pepper, rice, wheat.",
            "suggestions": ["Select a crop from the dropdown list."],
        }

    guide = guides[key]
    score, reasons = _score_crop(
        guide, soil_type, season, water_availability, temperature, None, humidity
    )

    if score >= 75:
        status, label = "suitable", "Suitable"
    elif score >= 50:
        status, label = "moderate", "Moderately Suitable"
    else:
        status, label = "not_suitable", "Not Suitable"

    suggestions = []
    if status != "suitable":
        if water_availability and guide.get("water") == "high":
            suggestions.append("Increase irrigation frequency or choose a drought-tolerant variety.")
        if soil_type and soil_type.lower() not in str(guide.get("soils", [])).lower():
            suggestions.append(f"Improve soil with organic matter to approach: {', '.join(guide['soils'])}.")
        suggestions.append("Consider adjusting planting season to: " + ", ".join(guide.get("seasons", [])))
    suggestions.append(guide.get("fertilizer", ""))

    explanation = " ".join(reasons)
    if location:
        explanation += f" Location context: {location}."

    return {
        "crop_name": guide["name"],
        "crop_key": key,
        "status": status,
        "label": label,
        "score": round(score, 1),
        "explanation": explanation,
        "suggestions": [s for s in suggestions if s],
    }


def get_cultivation_guide(crop_name):
    guides = _load_guides()
    key = _norm_crop(crop_name)
    if key not in guides:
        for k, g in guides.items():
            if crop_name and crop_name.lower() in g["name"].lower():
                key = k
                break
    if key not in guides:
        return None
    g = guides[key]
    return {
        "crop_name": g["name"],
        "crop_key": key,
        "best_season": ", ".join(g.get("seasons", [])),
        "soil_requirement": ", ".join(g.get("soils", [])),
        "water_requirement": g.get("water", "medium").title(),
        "fertilizer_requirement": g.get("fertilizer", ""),
        "sowing_method": g.get("sowing", ""),
        "irrigation_schedule": g.get("irrigation", ""),
        "pest_care": g.get("pest_care", ""),
        "harvesting_period": g.get("harvest", ""),
        "storage_tips": g.get("storage", ""),
        "timeline": g.get("timeline", []),
    }


def irrigation_advice(crop_name, growth_stage, soil_type, rainfall=None):
    guides = _load_guides()
    key = _norm_crop(crop_name)
    if key not in guides:
        return {"error": "Crop not found in guides."}
    g = guides[key]
    water_need = g.get("water", "medium")
    stage = (growth_stage or "vegetative").lower()

    freq_map = {
        "low": "Every 7-10 days if no rain",
        "medium": "Every 4-6 days if no rain",
        "high": "Every 2-4 days if no rain",
    }
    base_freq = freq_map.get(water_need, freq_map["medium"])

    if stage in ("flowering", "fruiting", "reproductive"):
        needed = True
        freq = "Increase frequency: " + base_freq.replace("Every", "Every").replace("4-6", "3-5").replace("7-10", "5-7")
        note = "Critical stage—avoid water stress during flowering and fruit set."
    elif stage == "seedling":
        needed = True
        freq = "Light frequent irrigation: every 2-3 days"
        note = "Keep topsoil moist but not waterlogged."
    elif stage == "maturity":
        needed = False
        freq = "Reduce irrigation 1-2 weeks before harvest"
        note = "Lower moisture improves harvest quality for many crops."
    else:
        needed = True
        freq = base_freq
        note = "Maintain even soil moisture in vegetative growth."

    if rainfall is not None:
        try:
            r = float(rainfall)
            if r > 15:
                needed = False
                freq = "Skip irrigation; recent rainfall is adequate"
                note = "Monitor drainage on clay soils."
            elif r > 5:
                freq = "Reduce schedule by 30-50%"
                note = "Supplement only if topsoil dries."
        except ValueError:
            pass

    if "clay" in (soil_type or "").lower():
        over = "Clay holds water—risk of root rot if over-irrigated."
        under = "Crusting possible—use drip and mulch."
    elif "sandy" in (soil_type or "").lower():
        over = "Sandy soil drains fast—short overwatering is less harmful than drought."
        under = "Frequent light irrigation preferred; mulch heavily."
    else:
        over = "Avoid prolonged saturated soil; improve drainage in low spots."
        under = "Check soil moisture at 10 cm depth before irrigating."

    return {
        "crop_name": g["name"],
        "irrigation_needed": needed,
        "frequency": freq,
        "stage_note": note,
        "overwatering_warning": over,
        "underwatering_warning": under,
        "water_saving_tips": [
            "Use drip irrigation to target root zones.",
            "Irrigate early morning to reduce evaporation.",
            "Apply organic mulch 5-8 cm deep.",
            "Monitor soil moisture before each cycle.",
        ],
    }


def fertilizer_advice(crop_name, growth_stage, soil_type, n=None, p=None, k=None, ph=None):
    guides = _load_guides()
    key = _norm_crop(crop_name)
    if key not in guides:
        return {"error": "Crop not found."}
    g = guides[key]
    stage = (growth_stage or "vegetative").lower()

    if stage in ("seedling", "vegetative"):
        nutrient = "Nitrogen-focused (moderate N, adequate P for roots)"
        fert_type = "Balanced starter 10-10-10 or compost tea"
        timing = "At planting and 3-4 weeks after emergence"
    elif stage in ("flowering", "fruiting"):
        nutrient = "Potassium and calcium focus; reduce excess nitrogen"
        fert_type = "Low N, higher K (e.g. 5-10-20) plus calcium source"
        timing = "At first flower and 2-3 week intervals during fruit set"
    else:
        nutrient = "Maintenance P and K; minimal N"
        fert_type = "Low nitrogen blend or organic compost"
        timing = "Only if deficiency symptoms appear"

    organic = "Compost, well-rotted manure, neem cake, and bone meal for P; wood ash for K."
    safety = "Never exceed label rates; avoid foliar spray in hot sun; wash produce per PHI."

    if ph is not None:
        try:
            phv = float(ph)
            if phv < 5.5:
                safety += " Low pH: consider lime before heavy fertilization."
            elif phv > 7.5:
                safety += " High pH: iron/zinc deficiency possible; acidify organic matter."
        except ValueError:
            pass

    if n is not None and p is not None and k is not None:
        nutrient += f" Your reported NPK ({n}-{p}-{k}) should be adjusted to stage needs."

    return {
        "crop_name": g["name"],
        "fertilizer_type": fert_type,
        "nutrient_focus": nutrient,
        "application_timing": timing,
        "organic_alternative": organic,
        "safety_warning": safety,
        "base_guide": g.get("fertilizer", ""),
    }


PEST_DATABASE = {
    "tomato": {
        "yellow leaves": {"name": "Nitrogen deficiency or overwatering", "cause": "Nutrient imbalance or poor drainage", "treatment": "Soil test; adjust N; improve drainage", "prevention": "Balanced fertilization; drip irrigation"},
        "brown spots": {"name": "Early blight or Septoria", "cause": "Fungal pathogens in warm humid weather", "treatment": "Remove lower leaves; fungicide per label", "prevention": "Mulch, stake, rotate crops"},
        "curling leaves": {"name": "Tomato yellow leaf curl virus", "cause": "Whitefly transmission", "treatment": "Remove infected plants; control whiteflies", "prevention": "Reflective mulch; resistant varieties"},
        "white powder": {"name": "Powdery mildew", "cause": "High humidity, poor airflow", "treatment": "Sulfur or potassium bicarbonate sprays", "prevention": "Prune for airflow; avoid overhead water"},
    },
    "potato": {
        "brown spots": {"name": "Early blight", "cause": "Alternaria solani", "treatment": "Fungicide program; remove infected foliage", "prevention": "Rotation; adequate nutrition"},
        "wilting": {"name": "Late blight or bacterial wilt", "cause": "Phytophthora or Ralstonia", "treatment": "Rogue plants; approved bactericides/fungicides", "prevention": "Certified seed; avoid wet foliage"},
    },
    "corn": {
        "holes in leaves": {"name": "Corn earworm / armyworm", "cause": "Lepidopteran larvae", "treatment": "Scout and treat at threshold; Bt products", "prevention": "Timely planting; field sanitation"},
        "rust": {"name": "Common rust", "cause": "Puccinia sorghi", "treatment": "Fungicide if before silking", "prevention": "Resistant hybrids"},
    },
    "default": {
        "yellow leaves": {"name": "Nutrient or water stress", "cause": "N deficiency, over/under watering", "treatment": "Soil test; adjust irrigation", "prevention": "Monitor soil moisture and fertility"},
        "brown spots": {"name": "Fungal leaf spot", "cause": "Humid conditions and spore spread", "treatment": "Remove debris; copper or chlorothalonil", "prevention": "Crop rotation; resistant varieties"},
        "wilting": {"name": "Water stress or root disease", "cause": "Drought or root rot pathogens", "treatment": "Check roots; adjust water; improve drainage", "prevention": "Drip irrigation; avoid compaction"},
        "chewed leaves": {"name": "Chewing insects", "cause": "Caterpillars or beetles", "treatment": "Hand pick; Bt or spinosad", "prevention": "Scout weekly; beneficial habitat"},
    },
}


def pest_disease_help(crop_name, symptom):
    key = _norm_crop(crop_name)
    symptom_l = (symptom or "").lower().strip()
    db = PEST_DATABASE.get(key, PEST_DATABASE["default"])
    match = None
    for sk, data in db.items():
        if sk in symptom_l or symptom_l in sk:
            match = data
            break
    if not match:
        for sk, data in PEST_DATABASE["default"].items():
            if sk in symptom_l:
                match = data
                break
    if not match:
        match = {
            "name": "General plant stress",
            "cause": "Multiple factors possible",
            "treatment": "Scout field; consider soil test and AI leaf scan",
            "prevention": "IPM practices and crop rotation",
        }
    return {
        "crop_name": crop_name,
        "symptom": symptom,
        "possible_issue": match["name"],
        "likely_cause": match["cause"],
        "treatment": match["treatment"],
        "prevention": match["prevention"],
    }

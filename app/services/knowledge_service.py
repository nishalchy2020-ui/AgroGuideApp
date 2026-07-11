import json
import re
from pathlib import Path

from app.models import DiseaseKnowledge

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "disease_knowledge.json"
_CROP_GUIDES_PATH = Path(__file__).resolve().parent.parent / "data" / "crop_guides.json"

COMMON_CROPS = (
    "apple", "apricot", "avocado", "banana", "barley", "bean", "beans",
    "blueberry", "brinjal", "broccoli", "cabbage", "carrot", "cassava",
    "cauliflower", "cherry", "cherries", "chickpea", "citrus", "cocoa",
    "coconut", "coffee", "cotton", "cucumber", "eggplant", "garlic",
    "grape", "grapes", "guava", "lentil", "lettuce", "lemon", "lime",
    "maize", "mango", "melon", "mustard", "okra", "onion", "orange",
    "papaya", "pea", "peas", "peach", "pear", "pepper", "pineapple",
    "plum", "pomegranate", "potato", "pumpkin", "rice", "sorghum",
    "soybean", "spinach", "squash", "strawberry", "sugarcane",
    "sunflower", "sweet potato", "tea", "tomato", "watermelon", "wheat",
    "yam", "zucchini",
)

APP_FEATURES = {
    "disease detection": (
        "Use Disease Detection to upload a clear leaf photo. AgroGuide returns the predicted "
        "disease, confidence, severity, treatment, prevention, and knowledge-base details."
    ),
    "crop recommendation": (
        "Use Crop Recommendation to enter soil, season, water, temperature, rainfall, and "
        "humidity. AgroGuide ranks crops with the bundled offline crop model."
    ),
    "crop suitability": (
        "Use Crop Suitability to choose a crop and field conditions. AgroGuide scores whether "
        "the crop is suitable and gives suggestions."
    ),
    "weather": (
        "Use Weather to search a location and get temperature, humidity, rainfall, farming "
        "advice, and disease-risk warnings."
    ),
    "history": (
        "Use History to review activity across scans, crop tools, weather searches, and chats."
    ),
    "admin": (
        "Admins can manage disease knowledge and view aggregate app activity from the admin panel."
    ),
}

AGRICULTURE_TERMS = re.compile(
    r"\b(agroguide|crop\w*|farm\w*|soil\w*|plant\w*|leaf|leaves|"
    r"disease\w*|pest\w*|fertiliz\w*|irrigat\w*|harvest\w*|seed\w*|"
    r"tomato\w*|potato\w*|corn|maize|rice|wheat|soybean\w*|onion\w*|"
    r"cherry|cherries|stone fruit|watermelon\w*|melon\w*|"
    r"cucumber\w*|pepper\w*|apple\w*|weather|rain\w*|humid\w*|organic|"
    r"npk|ph|blight\w*|rust|mite\w*|aphid\w*|compost|manure|greenhouse|"
    r"field\w*|agri\w*|grow\w*|sow\w*|mulch\w*|drip|spray\w*|fungic\w*|"
    r"herbic\w*|insect\w*|weed\w*|yield\w*|vegetable\w*|fruit\w*|"
    r"orchard\w*|root\w*|nitrogen|phosphor\w*|potassium)\b",
    re.I,
)
COMMON_CROP_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(crop) for crop in sorted(COMMON_CROPS, key=len, reverse=True)) + r")\b",
    re.I,
)

UNRELATED_MESSAGE = (
    "I can help with farming, crop care, plant disease, irrigation, fertilizer, "
    "pest control, weather-based farming advice, and AgroGuide app features."
)

GENERAL_RULES = [
    (
        r"\b(apple).*\b(scab|fung|spot|disease|reduce|prevent|control)\b|"
        r"\b(scab).*\b(apple)\b",
        "To reduce apple scab:\n"
        "1. Remove and destroy fallen infected leaves and fruit because the fungus overwinters in leaf litter.\n"
        "2. Prune trees to open the canopy so leaves dry faster after rain.\n"
        "3. Avoid overhead irrigation; water at the soil line when possible.\n"
        "4. Apply mulch after sanitation to reduce spore splash from old leaves.\n"
        "5. Plant resistant varieties where possible.\n"
        "6. Use a preventive fungicide program during bud break, green tip, bloom, and early fruit set if local disease pressure is high.\n"
        "7. Do not spray blindly; follow local extension guidance and product labels for timing and pre-harvest interval.\n"
        "8. Keep nitrogen balanced because dense soft growth increases humidity inside the canopy.",
    ),
    (
        r"\b(watermelon|watermelons|melon|melons)\b.*\b(step|steps|plant|grow|growing|cultivat|care|fertiliz|irrigat|water)?|"
        r"\b(step|steps|plant|grow|growing|cultivat|care|fertiliz|irrigat|water)\b.*\b(watermelon|watermelons|melon|melons)\b",
        "Watermelon growing guide:\n"
        "1. Plant in warm weather after frost risk has passed; soil should be warm for good germination.\n"
        "2. Choose full sun and loose, well-drained sandy loam or loam with pH around 6.0-7.0.\n"
        "3. Mix compost or well-rotted manure before planting; avoid heavy fresh manure.\n"
        "4. Sow seeds 2-3 cm deep or transplant carefully without disturbing roots.\n"
        "5. Space vines widely so leaves dry quickly and fruits have room to develop.\n"
        "6. Water deeply and consistently during vine growth, flowering, and fruit enlargement; reduce watering near harvest to improve sweetness.\n"
        "7. Use mulch to conserve moisture, suppress weeds, and keep fruit off wet soil.\n"
        "8. Fertilize with moderate nitrogen early, then shift toward potassium during flowering and fruiting.\n"
        "9. Watch for powdery mildew, downy mildew, aphids, fruit fly, and wilt; improve airflow and remove infected debris.\n"
        "10. Harvest when the field spot turns creamy yellow, tendril near the fruit dries, and rind sounds dull when tapped.",
    ),
    (
        r"\b(cherry|cherries|stone fruit)\b.*\b(step|steps|plant|grow|growing|cultivat|care|orchard)?|"
        r"\b(step|steps|plant|grow|growing|cultivat|care)\b.*\b(cherry|cherries|stone fruit)\b",
        "Detailed cherry growing steps:\n"
        "1. Choose a suitable type: sweet cherries need more space and often a pollinator; sour cherries are more self-fertile and compact.\n"
        "2. Select a sunny site with 6-8 hours of direct light and good air movement.\n"
        "3. Use deep, well-drained loam or sandy loam with pH around 6.0-7.0; avoid waterlogged clay.\n"
        "4. Plant during dormancy, keeping the graft union above soil level.\n"
        "5. Space trees by rootstock and type; dwarf trees need less space than standard trees.\n"
        "6. Water deeply after planting and keep soil evenly moist during establishment.\n"
        "7. Mulch 5-8 cm deep while keeping mulch away from the trunk.\n"
        "8. Prune to an open canopy for light and airflow; remove dead, crossing, or diseased branches.\n"
        "9. Fertilize lightly after growth starts; avoid excess nitrogen because it increases soft growth and disease risk.\n"
        "10. Scout for brown rot, bacterial canker, aphids, fruit fly, and birds; use sanitation, netting, and local extension guidance.",
    ),
    (
        r"\b(tomato).*(blight|spot|septoria|fung|yellow|brown)|\b(blight|septoria).*(tomato)\b",
        "For tomato leaf spots or blight, remove infected lower leaves, avoid overhead watering, stake plants for airflow, mulch to reduce soil splash, and rotate away from tomato/potato/pepper for 2-3 seasons. Use copper or approved fungicide only according to label and local guidance.",
    ),
    (
        r"\b(potato).*(blight|wilting|rot)|\b(blight).*(potato)\b",
        "For potato blight risk, use certified seed, destroy volunteer plants, avoid late evening irrigation, hill soil for tuber protection, and remove infected foliage. Preventive fungicide timing matters most before wet, cool weather.",
    ),
    (
        r"\b(rice).*(water|irrigation|fertilizer|nitrogen)|\b(paddy)\b",
        "Rice usually needs controlled flooding or saturated soil early, then careful drainage near maturity. Split nitrogen into basal, tillering, and panicle stages, and avoid excess nitrogen when disease pressure is high.",
    ),
    (
        r"\b(wheat).*(rust|fertilizer|irrigation)|\b(rust).*(wheat)\b",
        "For wheat, prioritize timely irrigation at crown-root initiation, booting, and grain filling. Rust risk rises with humid weather; use resistant varieties, balanced nitrogen, and scout lower leaves early.",
    ),
    (
        r"\b(fertilizer|fertiliz\w*|npk|nitrogen|phosphorus|potassium|compost|manure)\b",
        "Balanced NPK depends on crop stage: nitrogen supports leafy growth, phosphorus supports roots, and potassium supports flowering, fruiting, and stress tolerance. Use a soil test before applying fertilizer and avoid excess nitrogen during fruiting.",
    ),
    (
        r"\b(irrigation|irrigat\w*|water|drip|sprinkler|moisture)\b",
        "Water deeply and less often to encourage deeper roots. Drip irrigation reduces leaf wetness and disease risk. Check soil moisture near the root zone before irrigating.",
    ),
    (
        r"\b(pest|insect|aphid|mite|worm|beetle)\b",
        "Scout weekly and identify the pest before treatment. Start with cultural controls, remove heavily infested material, encourage beneficial insects, and follow label directions for any pesticide.",
    ),
    (
        r"\b(weather|rain|humidity|temperature|forecast|risk)\b",
        "Weather risk depends on crop stage. High humidity and leaf wetness raise fungal disease pressure, while heat and dry wind increase irrigation demand. Use AgroGuide Weather for location-based advice.",
    ),
    (
        r"\b(soil|ph|acid|alkaline)\b",
        "Most vegetables prefer soil pH around 6.0-7.0. Add organic matter to improve structure, drainage, and nutrient retention. Use lime or sulfur only after a soil test.",
    ),
    (
        r"\b(seedling|transplant|nursery|germination)\b",
        "For seedlings, use clean seed trays, light well-drained media, gentle watering, morning light, and good airflow. Avoid overwatering because damping-off disease spreads quickly in wet nursery conditions.",
    ),
    (
        r"\b(organic|neem|biological|biofertilizer|ipm)\b",
        "Organic and IPM programs work best when combined: resistant varieties, crop rotation, sanitation, beneficial habitat, compost, neem or biological products where appropriate, and regular scouting before pests reach damaging levels.",
    ),
]


def get_builtin_knowledge():
    if _DATA_PATH.exists():
        with open(_DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _load_crop_guides():
    if _CROP_GUIDES_PATH.exists():
        with open(_CROP_GUIDES_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _ratio(a, b):
    a = (a or "").lower()
    b = (b or "").lower()
    try:
        from rapidfuzz import fuzz

        return fuzz.partial_ratio(a, b) / 100
    except ImportError:
        from difflib import SequenceMatcher

        return SequenceMatcher(None, a, b).ratio()


def is_agriculture_or_app_query(question):
    text = (question or "").strip()
    if len(text) < 2:
        return False
    greetings = {"hi", "hello", "hey", "help", "thanks", "thank you"}
    if text.lower() in greetings:
        return True
    return bool(AGRICULTURE_TERMS.search(text) or COMMON_CROP_PATTERN.search(text))


def mentioned_common_crop(question):
    match = COMMON_CROP_PATTERN.search(question or "")
    return match.group(1).lower() if match else ""


def _score_text(question, *parts):
    haystack = " ".join(str(part or "") for part in parts)
    return _ratio(question, haystack)


def _app_feature_matches(question):
    question_l = (question or "").lower()
    if "agroguide" not in question_l and "app" not in question_l:
        return []

    matches = []
    for feature, answer in APP_FEATURES.items():
        feature_words = [word for word in feature.split() if len(word) > 3]
        has_feature_term = any(word in question_l for word in feature_words)
        if has_feature_term:
            score = max(0.75, _score_text(question, feature, answer))
            matches.append(
                {
                    "title": f"AgroGuide {feature.title()}",
                    "answer": answer,
                    "score": max(score, 0.7),
                    "source": "AgroGuide app",
                }
            )
    return matches


def _crop_guide_matches(question):
    matches = []
    question_l = (question or "").lower()
    for key, guide in _load_crop_guides().items():
        crop_mentioned = key in question_l or guide.get("name", "").lower() in question_l
        score = _score_text(
            question,
            key,
            guide.get("name"),
            guide.get("fertilizer"),
            guide.get("irrigation"),
            guide.get("pest_care"),
            guide.get("sowing"),
            guide.get("harvest"),
        )
        if crop_mentioned or score >= 0.65:
            answer = (
                f"{guide['name']} grows best in {', '.join(guide.get('seasons', []))} "
                f"with {', '.join(guide.get('soils', []))} soil and "
                f"{guide.get('water', 'medium')} water. "
                f"Fertilizer: {guide.get('fertilizer', '')} "
                f"Irrigation: {guide.get('irrigation', '')} "
                f"Pest care: {guide.get('pest_care', '')}"
            )
            matches.append(
                {
                    "title": guide["name"],
                    "answer": answer,
                    "score": max(score, 0.68),
                    "source": "AgroGuide crop guide",
                }
            )
    return matches


def _disease_matches(question):
    question_l = (question or "").lower()
    disease_intent = re.search(
        r"\b(disease\w*|blight\w*|rust|spot\w*|mildew|mold|virus|fung\w*|"
        r"bacteria\w*|wilting|yellow\w*|symptom\w*|lesion\w*|rot)\b",
        question_l,
    )
    if not disease_intent:
        return []

    crop_terms = [
        "apple",
        "corn",
        "maize",
        "pepper",
        "potato",
        "tomato",
    ]
    mentioned_crops = [crop for crop in crop_terms if crop in question_l]
    matches = []
    records = []
    for class_name, data in get_builtin_knowledge().items():
        records.append((class_name, data))
    try:
        for record in DiseaseKnowledge.query.all():
            records.append(
                (
                    record.class_name,
                    {
                        "description": record.description,
                        "symptoms": record.symptoms,
                        "causes": record.causes,
                        "treatment": record.treatment,
                        "prevention": record.prevention,
                        "organic_solution": record.organic_solution,
                    },
                )
            )
    except RuntimeError:
        pass

    seen = set()
    for class_name, data in records:
        if class_name in seen:
            continue
        seen.add(class_name)
        class_l = class_name.lower()
        if mentioned_crops and not any(crop in class_l for crop in mentioned_crops):
            continue
        score = _score_text(question, class_name, *data.values())
        if mentioned_crops:
            score = min(1.0, score + 0.2)
        if score >= 0.44 or class_name.lower().replace("_", " ") in question_l:
            label = class_name.replace("___", " ").replace("_", " ")
            answer = (
                f"{label}: {data.get('description', '')} "
                f"Symptoms: {data.get('symptoms', '')} "
                f"Treatment: {data.get('treatment', '')} "
                f"Prevention: {data.get('prevention', '')}"
            )
            matches.append(
                {
                    "title": label,
                    "answer": answer,
                    "score": max(score, 0.7),
                    "source": "AgroGuide disease knowledge",
                }
            )
    return matches


def general_farming_answer(question):
    for pattern, answer in GENERAL_RULES:
        if re.search(pattern, question or "", re.I):
            return answer, 0.74
    crop = mentioned_common_crop(question)
    if crop:
        return (
            f"I do not have a full local guide for {crop.title()} yet. "
            f"For {crop} farming, start with suitable local varieties, well-drained soil, "
            "balanced organic matter, correct planting season, steady irrigation, weed control, "
            "and weekly scouting for pests and disease. If online search or Gemini is configured, "
            "I will use it for more crop-specific guidance.",
            0.35,
        )
    return (
        "I do not have a specific local answer for that yet. Ask about a crop, disease, fertilizer, irrigation, pest control, weather risk, or an AgroGuide app feature.",
        0.25,
    )


def _rule_matches(question):
    matches = []
    for pattern, answer in GENERAL_RULES:
        if re.search(pattern, question or "", re.I):
            matches.append(
                {
                    "title": "AgroGuide farming rule",
                    "answer": answer,
                    "score": 0.9,
                    "source": "AgroGuide local rules",
                }
            )
            break
    return matches


def search_local_knowledge(question):
    """Return the strongest local AgroGuide answer and confidence."""
    if not is_agriculture_or_app_query(question):
        return {
            "answer": UNRELATED_MESSAGE,
            "confidence": 1.0,
            "source_type": "fallback",
            "sources": [],
            "is_relevant": False,
        }

    rule_matches = _rule_matches(question)
    disease_matches = _disease_matches(question)
    matches = rule_matches + disease_matches + _app_feature_matches(question)
    if not disease_matches:
        matches += _crop_guide_matches(question)
    if not matches:
        fallback, confidence = general_farming_answer(question)
        weak = confidence < 0.5
        return {
            "answer": fallback,
            "confidence": confidence,
            "source_type": "local" if not weak else "fallback",
            "sources": [{"name": "AgroGuide local rules", "url": None}],
            "is_relevant": True,
        }

    matches.sort(key=lambda item: item["score"], reverse=True)
    best = matches[0]
    return {
        "answer": best["answer"],
        "confidence": min(1.0, best["score"]),
        "source_type": "local",
        "sources": [{"name": best["source"], "url": None}],
        "is_relevant": True,
    }


def get_knowledge_for_class(class_name: str):
    record = DiseaseKnowledge.query.filter_by(class_name=class_name).first()
    if record:
        return {
            "description": record.description,
            "symptoms": record.symptoms,
            "causes": record.causes,
            "treatment": record.treatment,
            "prevention": record.prevention,
            "severity": record.severity,
            "pesticide": record.pesticide,
            "organic_solution": record.organic_solution,
        }
    builtin = get_builtin_knowledge()
    if class_name in builtin:
        return builtin[class_name]
    return {
        "description": "Detailed knowledge for this class is not yet in the database.",
        "symptoms": "Consult local extension services for symptom identification.",
        "causes": "Varies by pathogen and environmental conditions.",
        "treatment": "Follow integrated pest management guidelines.",
        "prevention": "Crop rotation, sanitation, resistant varieties.",
        "severity": "medium",
        "pesticide": "Use EPA-registered products per label.",
        "organic_solution": "Neem, copper, or biological controls as appropriate.",
    }


def severity_badge_class(severity: str) -> str:
    mapping = {
        "low": "badge-low",
        "medium": "badge-medium",
        "high": "badge-high",
    }
    return mapping.get((severity or "low").lower(), "badge-medium")

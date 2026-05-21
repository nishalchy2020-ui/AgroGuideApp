import json

from app import db
from app.models import ActivityHistory

MODULE_LABELS = {
    "disease_scan": "AI Disease Detection",
    "weather": "Weather",
    "chatbot": "AI Assistant",
    "crop_recommendation": "Crop Recommendation",
    "crop_suitability": "Crop Suitability",
    "cultivation_guide": "Cultivation Guide",
    "irrigation": "Irrigation Advice",
    "fertilizer": "Fertilizer Guidance",
    "pest_help": "Pest & Disease Help",
}


def log_activity(user_id, module, title, summary=None, ref_id=None):
    record = ActivityHistory(
        user_id=user_id,
        module=module,
        title=title[:255],
        summary=json.dumps(summary or {}, default=str)[:8000],
        ref_id=ref_id,
    )
    db.session.add(record)
    return record


def module_label(module):
    return MODULE_LABELS.get(module, module.replace("_", " ").title())

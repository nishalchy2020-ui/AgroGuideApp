from app.services.knowledge_service import (
    UNRELATED_MESSAGE,
    is_agriculture_or_app_query,
    search_local_knowledge,
)
from app.services.search_service import SearchUnavailable, safe_search_answer

LOCAL_CONFIDENCE_THRESHOLD = 0.66


def generate_hybrid_reply(user_message, conversation=None):
    """
    Return a dict with reply, source_type, sources, and error.
    Local AgroGuide knowledge is always tried before internet search.
    """
    if not is_agriculture_or_app_query(user_message):
        return {
            "reply": UNRELATED_MESSAGE,
            "source_type": "fallback",
            "sources": [],
            "error": False,
        }

    local = search_local_knowledge(user_message)
    if local["confidence"] >= LOCAL_CONFIDENCE_THRESHOLD:
        return {
            "reply": _format_local_answer(local["answer"]),
            "source_type": "local",
            "sources": local.get("sources", []),
            "error": False,
        }

    try:
        internet_answer, sources = safe_search_answer(user_message)
        return {
            "reply": internet_answer,
            "source_type": "internet",
            "sources": [
                {"name": item.get("title") or "Source", "url": item.get("url")}
                for item in sources[:3]
            ],
            "error": False,
        }
    except SearchUnavailable:
        prefix = (
            "I could not access online sources right now, but here is general farming guidance.\n\n"
        )
        return {
            "reply": prefix + _format_local_answer(local["answer"]),
            "source_type": "fallback",
            "sources": local.get("sources", []),
            "error": True,
        }


def _format_local_answer(answer):
    return (
        answer
        + "\n\nSource: Local AgroGuide knowledge.\n"
        + "Regional note: Adjust recommendations for your crop variety, soil test, weather, and local extension guidance."
    )


def get_chatbot_response(message: str) -> str:
    """Backward-compatible helper used by older code paths."""
    return generate_hybrid_reply(message)["reply"]

import re

from app.services.knowledge_service import (
    UNRELATED_MESSAGE,
    is_agriculture_or_app_query,
    mentioned_common_crop,
    search_local_knowledge,
)
from app.services.gemini_service import GeminiStreamError, generate_rag_reply, generate_rag_reply_stream
from app.services.search_service import SearchUnavailable, search_all_sources

LOCAL_CONFIDENCE_THRESHOLD = 0.66

_CITATION_ARTIFACT = re.compile(
    r"\s*\[(?:\s*\d+(?:\s*,\s*\d+)*\s*(?:,\s*supplemental search context\s*)?"
    r"|\s*supplemental search context\s*)\]",
    re.IGNORECASE,
)


def strip_citation_artifacts(text):
    """Remove model-generated citation markers; source links are rendered separately."""
    return _CITATION_ARTIFACT.sub("", text or "")


def generate_hybrid_reply(user_message, conversation=None, user_context=None):
    """
    Return a dict with reply, source_type, sources, and error.
    Local AgroGuide knowledge is always tried before internet search.
    """
    contextual_message = _contextualize_followup(user_message, conversation)

    if not is_agriculture_or_app_query(contextual_message):
        return {
            "reply": UNRELATED_MESSAGE,
            "source_type": "fallback",
            "sources": [],
            "error": False,
        }

    context_note = _format_context_note(user_context, user_message)
    local = search_local_knowledge(contextual_message)
    evidence = _local_evidence(local)
    search_error = None
    try:
        evidence.extend(search_all_sources(f"{contextual_message} agriculture farming crop advice"))
    except SearchUnavailable as exc:
        search_error = str(exc)

    contextual_conversation = _conversation_with_context(conversation, user_context)
    gemini_reply, gemini_error = generate_rag_reply(
        contextual_message,
        evidence=evidence,
        conversation=contextual_conversation,
        user_context=user_context,
    )
    if gemini_reply and not _is_gemini_scope_refusal(gemini_reply):
        return {
            "reply": strip_citation_artifacts(_append_context_note(gemini_reply, context_note)),
            "source_type": "rag",
            "sources": _response_sources(evidence),
            "error": False,
        }

    if local["confidence"] >= LOCAL_CONFIDENCE_THRESHOLD:
        return {
            "reply": _format_local_answer(local["answer"], context_note),
            "source_type": "local",
            "sources": local.get("sources", []),
            "error": False,
        }

    if len(evidence) > len(_local_evidence(local)):
        answer = _fallback_from_evidence(contextual_message, evidence)
        return {
            "reply": _append_context_note(answer, context_note),
            "source_type": "internet",
            "sources": _response_sources(evidence),
            "error": False,
        }

    prefix = "AI generation and web retrieval are unavailable right now, so here is practical farming guidance.\n\n"
    fallback_answer = local["answer"] if local["confidence"] >= 0.5 else _practical_unknown_crop_answer(contextual_message)
    return {
        "reply": prefix + _format_local_answer(fallback_answer, context_note),
        "source_type": "fallback",
        "sources": local.get("sources", []),
        "error": True,
        "debug_error": gemini_error or search_error,
    }


def _format_local_answer(answer, context_note=""):
    text = (
        answer
        + "\n\nSource: Local AgroGuide knowledge.\n"
        + "Regional note: Adjust recommendations for your crop variety, soil test, weather, and local extension guidance."
    )
    return _append_context_note(text, context_note)


def _local_evidence(local):
    if not local or not local.get("answer"):
        return []
    return [
        {
            "title": (local.get("sources") or [{"name": "AgroGuide local knowledge"}])[0].get("name"),
            "snippet": local["answer"],
            "url": None,
            "source": "local",
        }
    ]


def _response_sources(evidence):
    sources = []
    for item in evidence[:8]:
        url = item.get("url") or ""
        if (
            item.get("source") == "local"
            or not url.startswith(("http://", "https://"))
            or not (item.get("snippet") or item.get("answer"))
        ):
            continue
        name = item.get("title") or item.get("source") or "Source"
        sources.append({"name": name, "url": url})
    return sources


def _text_chunks(text, words_per_chunk=7):
    words = re.findall(r"\S+\s*", text or "")
    for start in range(0, len(words), words_per_chunk):
        yield "".join(words[start:start + words_per_chunk])


def generate_hybrid_reply_stream(user_message, conversation=None, user_context=None):
    """Yield progress events while building one complete final result."""
    yield {"type": "status", "message": "Reading your prompt"}
    contextual_message = _contextualize_followup(user_message, conversation)
    yield {"type": "status", "message": "Thinking"}

    if not is_agriculture_or_app_query(contextual_message):
        result = {
            "reply": UNRELATED_MESSAGE,
            "source_type": "fallback",
            "sources": [],
            "error": False,
        }
        yield {"type": "status", "message": "Just a sec"}
        yield {"type": "result", "result": result}
        return

    context_note = _format_context_note(user_context, user_message)
    yield {"type": "status", "message": "Searching local knowledge"}
    local = search_local_knowledge(contextual_message)
    local_evidence = _local_evidence(local)
    evidence = list(local_evidence)
    search_error = None
    yield {"type": "status", "message": "Using RAG"}
    try:
        evidence.extend(search_all_sources(f"{contextual_message} agriculture farming crop advice"))
    except SearchUnavailable as exc:
        search_error = str(exc)

    contextual_conversation = _conversation_with_context(conversation, user_context)
    reply_parts = []
    gemini_error = None
    try:
        for chunk in generate_rag_reply_stream(
            contextual_message,
            evidence=evidence,
            conversation=contextual_conversation,
            user_context=user_context,
        ):
            reply_parts.append(chunk)
    except GeminiStreamError as exc:
        gemini_error = str(exc)

    gemini_reply = strip_citation_artifacts("".join(reply_parts)).strip()
    if gemini_reply:
        context_suffix = _append_context_note("", context_note)
        if context_suffix:
            reply_parts.append(context_suffix)
        result = {
            "reply": strip_citation_artifacts("".join(reply_parts)).strip(),
            "source_type": "rag",
            "sources": _response_sources(evidence),
            "error": False,
        }
        yield {"type": "status", "message": "Just a sec"}
        yield {"type": "result", "result": result}
        return

    if local["confidence"] >= LOCAL_CONFIDENCE_THRESHOLD:
        result = {
            "reply": _format_local_answer(local["answer"], context_note),
            "source_type": "local",
            "sources": [],
            "error": False,
        }
    elif len(evidence) > len(local_evidence):
        result = {
            "reply": _append_context_note(
                _fallback_from_evidence(contextual_message, evidence), context_note
            ),
            "source_type": "internet",
            "sources": _response_sources(evidence),
            "error": False,
        }
    else:
        fallback_answer = (
            local["answer"]
            if local["confidence"] >= 0.5
            else _practical_unknown_crop_answer(contextual_message)
        )
        result = {
            "reply": (
                "AI generation and web retrieval are unavailable right now, so here is "
                "practical farming guidance.\n\n"
                + _format_local_answer(fallback_answer, context_note)
            ),
            "source_type": "fallback",
            "sources": [],
            "error": True,
            "debug_error": gemini_error or search_error,
        }

    yield {"type": "status", "message": "Just a sec"}
    yield {"type": "result", "result": result}


def _fallback_from_evidence(question, evidence):
    useful = [
        item for item in evidence
        if item.get("source") != "local" and item.get("snippet")
    ]
    if not useful:
        useful = [item for item in evidence if item.get("snippet")]
    direct = " ".join(item["snippet"] for item in useful[:2])
    direct = " ".join(direct.split())
    if len(direct) > 700:
        direct = direct[:700].rsplit(" ", 1)[0] + "."
    crop = _mentioned_crop(question)
    lead = f"For {crop.title()}, " if crop else ""
    return (
        lead
        + direct
        + "\n\nPractical next steps: verify the advice against your local season, soil test, water availability, and extension guidance before applying fertilizers or pesticides."
    )


def _contextualize_followup(user_message, conversation=None):
    text = (user_message or "").strip()
    if not text:
        return text
    if is_agriculture_or_app_query(text):
        return text

    topic = _last_agriculture_topic(conversation or [])
    if not topic:
        return text

    followup_patterns = (
        "detail",
        "details",
        "step",
        "steps",
        "how",
        "what",
        "when",
        "where",
        "why",
        "give me",
        "tell me",
        "explain",
        "more",
        "continue",
        "next",
        "plant",
        "grow",
    )
    lowered = text.lower()
    short_followup = len(lowered.split()) <= 6
    if short_followup or any(pattern in lowered for pattern in followup_patterns):
        return f"{text} about {topic}"
    return text


def _last_agriculture_topic(conversation):
    practice_terms = (
        "fertilizer",
        "irrigation",
        "soil",
        "pest",
        "disease",
        "blight",
        "weather",
        "planting",
    )
    for message in reversed(conversation[-8:]):
        content = (message.get("content") or "").lower()
        crop = mentioned_common_crop(content)
        if crop:
            return _canonical_crop(crop)
        for term in practice_terms:
            if term in content:
                return term
    return ""


def _conversation_with_context(conversation, user_context):
    context_summary = (user_context or {}).get("summary", "").strip()
    if not context_summary:
        return conversation
    context_message = {
        "role": "assistant",
        "content": (
            "User AgroGuide context for personalization: "
            + context_summary
            + " Use this only for farming advice and do not invent missing details."
        ),
    }
    return [context_message] + list(conversation or [])


def _format_context_note(user_context, user_message):
    summary = (user_context or {}).get("summary", "").strip()
    if not summary:
        return ""

    text = (user_message or "").lower()
    mentioned_crop = _mentioned_crop(text)
    history_crops = set((user_context or {}).get("disease", {}).get("crops", []))
    if mentioned_crop and history_crops and mentioned_crop not in history_crops:
        return ""

    context_pattern = (
        r"\b(my|history|scan|previous|recommend|advice|next|"
        r"irrigation|fertilizer|disease|crop)\b|what should"
    )
    if not re.search(context_pattern, text):
        return ""
    return summary


def _mentioned_crop(text):
    return _canonical_crop(mentioned_common_crop(text))


def _canonical_crop(crop):
    aliases = {
        "cherries": "cherry",
        "watermelons": "watermelon",
        "melons": "watermelon",
        "melon": "watermelon",
        "maize": "corn",
        "brinjal": "eggplant",
        "grapes": "grape",
        "beans": "bean",
        "peas": "pea",
    }
    return aliases.get((crop or "").lower(), (crop or "").lower())


def _append_context_note(answer, context_note):
    if not context_note:
        return answer
    return (
        answer
        + "\n\nPersonalized AgroGuide context: "
        + context_note
    )


def _is_gemini_scope_refusal(reply):
    text = (reply or "").lower()
    return (
        "i can only help with agriculture" in text
        or "please ask a farming-related question" in text
    )


def _practical_unknown_crop_answer(question):
    crop = _mentioned_crop(question)
    if crop:
        return (
            f"For {crop.title()}, I do not have a complete built-in crop profile yet, "
            "but you can use this practical plan:\n"
            "1. Choose a locally adapted variety and confirm the best planting season for your region.\n"
            "2. Prepare well-drained soil with compost or decomposed manure.\n"
            "3. Keep soil moisture steady, avoiding both drought stress and waterlogging.\n"
            "4. Use a soil test before fertilizer; avoid excess nitrogen during flowering or fruiting.\n"
            "5. Scout weekly for pests, leaf spots, wilting, and nutrient deficiency symptoms.\n"
            "6. Use mulch, spacing, pruning, and sanitation to reduce disease pressure.\n"
            "7. Check local extension guidance for exact spacing, pesticide labels, and harvest timing."
        )
    return (
        "I can help if you give me the crop name, growth stage, location or season, "
        "soil type, water availability, and the problem you are seeing. For example: "
        "'How do I grow mango in sandy soil?' or 'What should I do for yellow tomato leaves?'"
    )


def get_chatbot_response(message: str) -> str:
    """Backward-compatible helper used by older code paths."""
    return generate_hybrid_reply(message)["reply"]

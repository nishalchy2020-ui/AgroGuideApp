import logging
import re
import time

SYSTEM_INSTRUCTION = (
    "You are AgroGuide AI, a smart farming assistant. Only answer agriculture-related "
    "questions such as crop care, plant disease, irrigation, fertilizer, weather risks, "
    "pest management, and sustainable farming. Give clear, practical, farmer-friendly advice. "
    "Keep responses concise (under 200 words unless detail is essential). "
    "If asked about non-farming topics, politely redirect to farming support only."
)

AGRI_PATTERN = re.compile(
    r"\b(crop|farm|soil|plant|leaf|disease|pest|fertiliz|irrigat|harvest|"
    r"seed|tomato|potato|corn|maize|cherry|cherries|watermelon|melon|"
    r"mango|banana|citrus|orange|lemon|lime|grape|strawberry|blueberry|"
    r"peach|pear|plum|apricot|avocado|coconut|papaya|pineapple|guava|"
    r"pomegranate|okra|eggplant|brinjal|cabbage|cauliflower|broccoli|"
    r"carrot|lettuce|spinach|bean|pea|lentil|chickpea|mustard|sunflower|"
    r"sugarcane|cotton|tea|coffee|cocoa|cassava|yam|pumpkin|squash|zucchini|"
    r"weather|rain|humid|organic|npk|ph|"
    r"blight|rust|mite|aphid|compost|manure|greenhouse|field|agri|grow|"
    r"sow|till|mulch|drip|spray|fungic|herbic|insect|weed|yield|"
    r"vegetable|fruit|orchard|vine|root|nitrogen|phosphor|potassium)\b",
    re.I,
)

GEMINI_MISSING_MESSAGE = (
    "Gemini API key is not configured. Add GEMINI_API_KEY to your .env file "
    "(see .env.example) and restart the application."
)

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
FALLBACK_GEMINI_MODEL = "gemini-2.5-flash"
DEPRECATED_MODEL_ALIASES = {
    "gemini-pro": DEFAULT_GEMINI_MODEL,
    "gemini-1.0-pro": DEFAULT_GEMINI_MODEL,
    "gemini-1.5-flash": DEFAULT_GEMINI_MODEL,
    "gemini-2.0-flash": DEFAULT_GEMINI_MODEL,
    "gemini-2.0-flash-lite": DEFAULT_GEMINI_MODEL,
}
_logger = logging.getLogger("agroguide")
_quota_block_until = 0


def _normalize_model_name(model_name: str) -> str:
    name = (model_name or DEFAULT_GEMINI_MODEL).strip()
    if not name or "preview" in name.lower():
        return DEFAULT_GEMINI_MODEL
    return DEPRECATED_MODEL_ALIASES.get(name, name)


def _gemini_settings():
    """Read Gemini settings from Flask config (loaded from .env via config.py)."""
    from flask import current_app

    api_key = (current_app.config.get("GEMINI_API_KEY") or "").strip()
    model_name = _normalize_model_name(current_app.config.get("GEMINI_MODEL"))
    return api_key, model_name


def validate_gemini_startup(app):
    """Validate Gemini settings at startup without preventing Flask from booting."""
    api_key = (app.config.get("GEMINI_API_KEY") or "").strip()
    raw_model = (app.config.get("GEMINI_MODEL") or "").strip()
    model_name = _normalize_model_name(raw_model)

    if not api_key:
        app.logger.warning(
            "GEMINI_API_KEY is not set. AI Assistant will return a configuration message."
        )
        return

    if not raw_model:
        app.logger.warning(
            "GEMINI_MODEL is not set. Using %s.", DEFAULT_GEMINI_MODEL
        )
    elif raw_model != model_name:
        app.logger.warning(
            "GEMINI_MODEL=%s is deprecated or unsupported. Using %s.",
            raw_model,
            model_name,
        )

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        client.models.get(model=model_name)
    except (ImportError, ModuleNotFoundError):
        app.logger.error(
            "google-genai is not installed. Run: pip install -r requirements.txt"
        )
    except Exception as exc:
        app.logger.exception(
            "Gemini startup validation failed for model %s. Check GEMINI_API_KEY, "
            "GEMINI_MODEL, network access, and Google AI Studio model availability.",
            model_name,
        )
        if model_name != FALLBACK_GEMINI_MODEL:
            app.logger.warning(
                "If %s is unavailable for your key or region, set GEMINI_MODEL=%s.",
                model_name,
                FALLBACK_GEMINI_MODEL,
            )
    else:
        app.logger.info("Gemini startup validation succeeded (model=%s).", model_name)


def is_agriculture_query(text: str) -> bool:
    t = (text or "").strip().lower()
    if len(t) < 3:
        return False
    if AGRI_PATTERN.search(t):
        return True
    greetings = ("hello", "hi", "hey", "help", "thanks", "thank you")
    return any(t.startswith(g) for g in greetings)


def _build_prompt(user_message: str, conversation=None) -> str:
    recent = []
    for msg in (conversation or [])[-10:]:
        role = "Farmer" if msg.get("role") == "user" else "AgroGuide AI"
        content = (msg.get("content") or "").strip()
        if content:
            recent.append(f"{role}: {content}")

    if not recent:
        return user_message

    return (
        "Recent conversation:\n"
        + "\n".join(recent)
        + "\n\nFarmer's new question:\n"
        + user_message
    )


def _build_rag_prompt(user_message: str, evidence=None, conversation=None, user_context=None) -> str:
    sections = []
    context_summary = (user_context or {}).get("summary", "").strip()
    if context_summary:
        sections.append(
            "User AgroGuide context. Use only if relevant to the user's current crop/problem:\n"
            + context_summary
        )

    recent = []
    for msg in (conversation or [])[-8:]:
        role = "Farmer" if msg.get("role") == "user" else "AgroGuide AI"
        content = (msg.get("content") or "").strip()
        if content:
            recent.append(f"{role}: {content[:500]}")
    if recent:
        sections.append("Recent chat:\n" + "\n".join(recent))

    local_lines = []
    supplemental_lines = []
    external_lines = []
    for item in (evidence or [])[:8]:
        title = item.get("title") or item.get("name") or "Retrieved source"
        source = item.get("source") or item.get("provider") or "retrieved"
        url = item.get("url") or ""
        snippet = " ".join(str(item.get("snippet") or item.get("answer") or "").split())
        if len(snippet) > 700:
            snippet = snippet[:700].rsplit(" ", 1)[0] + "."
        if not snippet:
            continue
        if source == "local":
            local_lines.append(f"{title}\n{snippet}")
        elif url.startswith(("http://", "https://")):
            external_lines.append(f"{title} ({source}) {url}\n{snippet}")
        else:
            supplemental_lines.append(f"{title} ({source})\n{snippet}")

    if local_lines:
        sections.append("Local AgroGuide knowledge (do not cite with a number):\n" + "\n\n".join(local_lines))
    if supplemental_lines:
        sections.append("Supplemental search context (do not cite with a number):\n" + "\n\n".join(supplemental_lines))
    if external_lines:
        sections.append("External sources:\n" + "\n\n".join(external_lines))

    instructions = (
        "Answer as AgroGuide AI using the retrieved evidence and recent chat context. "
        "Stay strictly on agriculture/farming. If sources conflict, prefer local AgroGuide "
        "knowledge and university/extension/government sources. Give practical steps. "
        "Do not put citations, reference numbers, source labels, source names, or URLs in "
        "the answer text. In particular, never output bracketed markers such as [1], "
        "[1, 2], or [Supplemental search context]. The interface displays external sources "
        "separately below the answer. "
        "Do not mention irrelevant user history. If evidence is weak, say what information "
        "is missing and provide safe general farming guidance."
    )
    return (
        instructions
        + "\n\n"
        + "\n\n".join(sections)
        + "\n\nFarmer's current question:\n"
        + user_message
    )


def _candidate_model_names(model_name: str):
    primary = _normalize_model_name(model_name)
    yield primary
    if primary != FALLBACK_GEMINI_MODEL:
        yield FALLBACK_GEMINI_MODEL


def _is_quota_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "resource_exhausted" in message or "quota exceeded" in message


def _is_transient_model_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "503" in message
        or "unavailable" in message
        or "high demand" in message
        or "temporarily" in message
    )


def generate_reply(user_message: str, conversation=None):
    """
    Returns (reply_text, error_message).
    When the API key is missing or the call fails, reply_text is None and
    error_message contains a user-friendly message (no crash).
    """
    global _quota_block_until

    try:
        api_key, model_name = _gemini_settings()
    except RuntimeError:
        from config import getenv

        api_key = (getenv("GEMINI_API_KEY") or "").strip()
        model_name = _normalize_model_name(getenv("GEMINI_MODEL"))

    if not api_key:
        return None, GEMINI_MISSING_MESSAGE

    if time.time() < _quota_block_until:
        return (
            None,
            "AgroGuide AI is temporarily rate-limited, so I will use local knowledge or search.",
        )

    if not is_agriculture_query(user_message):
        return (
            "I can only help with agriculture and farming topics such as crops, soil, "
            "irrigation, fertilizer, pests, diseases, and weather risks. "
            "Please ask a farming-related question.",
            None,
        )

    try:
        from google import genai
        from google.genai import types
    except (ImportError, ModuleNotFoundError):
        return (
            None,
            "The Google Gemini client library is not installed. From your project folder run: "
            "pip install google-genai "
            "(or pip install -r requirements.txt), then restart the app.",
        )

    prompt = _build_prompt(user_message, conversation=conversation)
    try:
        client = genai.Client(api_key=api_key)
    except Exception as exc:
        _logger.exception("Failed to initialize Gemini client.")
        return (
            None,
            f"AgroGuide AI is temporarily unavailable. ({exc.__class__.__name__}) "
            "Check your API key and Gemini SDK installation, then try again.",
        )

    last_exc = None
    last_failed_model = None
    for candidate_model in _candidate_model_names(model_name):
        try:
            response = client.models.generate_content(
                model=candidate_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                ),
            )
            text = (response.text or "").strip()
            if not text:
                return (
                    "I could not generate a response. Please try rephrasing your question.",
                    None,
                )
            return text, None
        except Exception as exc:
            last_exc = exc
            last_failed_model = candidate_model
            if _is_quota_error(exc):
                _quota_block_until = time.time() + 60
                _logger.warning(
                    "Gemini quota exhausted for model %s; pausing Gemini calls briefly.",
                    candidate_model,
                )
                break
            if _is_transient_model_error(exc):
                _logger.warning(
                    "Gemini model %s is temporarily unavailable; trying fallback if available.",
                    candidate_model,
                )
            else:
                _logger.exception(
                    "Gemini generate_content failed for model %s.", candidate_model
                )
            if candidate_model == FALLBACK_GEMINI_MODEL:
                break
            _logger.warning(
                "Retrying Gemini request with fallback model %s.",
                FALLBACK_GEMINI_MODEL,
            )

    exc = last_exc or RuntimeError("Unknown Gemini API error")
    if _is_quota_error(exc):
        return (
            None,
            "AgroGuide AI reached the free Gemini API quota for this API key/project. "
            "Please wait for the free quota to reset, or use another free Gemini API key "
            "from Google AI Studio.",
        )

    hint = ""
    if (
        last_failed_model != FALLBACK_GEMINI_MODEL
        and ("404" in str(exc) or "not found" in str(exc).lower())
    ):
        hint = f" Try GEMINI_MODEL={FALLBACK_GEMINI_MODEL} in .env."
    return (
        None,
        f"AgroGuide AI is temporarily unavailable. ({exc.__class__.__name__}) "
        f"Check your API key, model name, and network, then try again.{hint}",
    )


def generate_rag_reply(user_message: str, evidence=None, conversation=None, user_context=None):
    prompt = _build_rag_prompt(
        user_message,
        evidence=evidence,
        conversation=conversation,
        user_context=user_context,
    )
    return generate_reply(prompt, conversation=[])


class GeminiStreamError(RuntimeError):
    """Raised when Gemini cannot start or complete a streamed response."""


def generate_rag_reply_stream(user_message: str, evidence=None, conversation=None, user_context=None):
    """Yield Gemini response text as the SDK produces it."""
    global _quota_block_until

    prompt = _build_rag_prompt(
        user_message,
        evidence=evidence,
        conversation=conversation,
        user_context=user_context,
    )

    try:
        api_key, model_name = _gemini_settings()
    except RuntimeError:
        from config import getenv

        api_key = (getenv("GEMINI_API_KEY") or "").strip()
        model_name = _normalize_model_name(getenv("GEMINI_MODEL"))

    if not api_key:
        raise GeminiStreamError(GEMINI_MISSING_MESSAGE)
    if time.time() < _quota_block_until:
        raise GeminiStreamError("AgroGuide AI is temporarily rate-limited.")

    try:
        from google import genai
        from google.genai import types
    except (ImportError, ModuleNotFoundError) as exc:
        raise GeminiStreamError("The Google Gemini client library is not installed.") from exc

    try:
        client = genai.Client(api_key=api_key)
    except Exception as exc:
        raise GeminiStreamError("Gemini could not be initialized.") from exc

    last_exc = None
    for candidate_model in _candidate_model_names(model_name):
        emitted = False
        try:
            response_stream = client.models.generate_content_stream(
                model=candidate_model,
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION),
            )
            for response_chunk in response_stream:
                text = response_chunk.text or ""
                if text:
                    emitted = True
                    yield text
            if emitted:
                return
        except Exception as exc:
            last_exc = exc
            if _is_quota_error(exc):
                _quota_block_until = time.time() + 60
            if emitted or candidate_model == FALLBACK_GEMINI_MODEL:
                break
            _logger.warning(
                "Gemini streaming failed for %s; trying %s.",
                candidate_model,
                FALLBACK_GEMINI_MODEL,
            )

    raise GeminiStreamError(str(last_exc or "Gemini returned no streamed text."))

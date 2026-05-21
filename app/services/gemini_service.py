import logging
import re

SYSTEM_INSTRUCTION = (
    "You are AgroGuide AI, a smart farming assistant. Only answer agriculture-related "
    "questions such as crop care, plant disease, irrigation, fertilizer, weather risks, "
    "pest management, and sustainable farming. Give clear, practical, farmer-friendly advice. "
    "Keep responses concise (under 200 words unless detail is essential). "
    "If asked about non-farming topics, politely redirect to farming support only."
)

AGRI_PATTERN = re.compile(
    r"\b(crop|farm|soil|plant|leaf|disease|pest|fertiliz|irrigat|harvest|"
    r"seed|tomato|potato|corn|maize|weather|rain|humid|organic|npk|ph|"
    r"blight|rust|mite|aphid|compost|manure|greenhouse|field|agri|grow|"
    r"sow|till|mulch|drip|spray|fungic|herbic|insect|weed|yield|"
    r"vegetable|fruit|orchard|vine|root|nitrogen|phosphor|potassium)\b",
    re.I,
)

GEMINI_MISSING_MESSAGE = (
    "Gemini API key is not configured. Add GEMINI_API_KEY to your .env file "
    "(see .env.example) and restart the application."
)

DEFAULT_GEMINI_MODEL = "gemini-2.0-flash-lite"
FALLBACK_GEMINI_MODEL = "gemini-2.0-flash"
DEPRECATED_MODEL_ALIASES = {
    "gemini-pro": DEFAULT_GEMINI_MODEL,
    "gemini-1.0-pro": DEFAULT_GEMINI_MODEL,
    "gemini-1.5-flash": DEFAULT_GEMINI_MODEL,
}
_logger = logging.getLogger("agroguide")


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


def _candidate_model_names(model_name: str):
    primary = _normalize_model_name(model_name)
    yield primary
    if primary != FALLBACK_GEMINI_MODEL:
        yield FALLBACK_GEMINI_MODEL


def _is_quota_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "resource_exhausted" in message or "quota exceeded" in message


def generate_reply(user_message: str, conversation=None):
    """
    Returns (reply_text, error_message).
    When the API key is missing or the call fails, reply_text is None and
    error_message contains a user-friendly message (no crash).
    """
    try:
        api_key, model_name = _gemini_settings()
    except RuntimeError:
        from config import getenv

        api_key = (getenv("GEMINI_API_KEY") or "").strip()
        model_name = _normalize_model_name(getenv("GEMINI_MODEL"))

    if not api_key:
        return None, GEMINI_MISSING_MESSAGE

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
            _logger.exception(
                "Gemini generate_content failed for model %s.", candidate_model
            )
            if _is_quota_error(exc):
                break
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

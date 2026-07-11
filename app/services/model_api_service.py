import logging
from pathlib import Path

import requests
from flask import current_app
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("agroguide.model_api")

_http = requests.Session()
_retry = Retry(
    total=2,
    backoff_factor=0.6,
    status_forcelist=(502, 503, 504),
    allowed_methods=frozenset(["POST"]),
)
_http.mount("http://", HTTPAdapter(max_retries=_retry))
_http.mount("https://", HTTPAdapter(max_retries=_retry))


class ModelApiError(RuntimeError):
    """User-safe error raised when the remote model API cannot return a prediction."""


def is_model_api_configured():
    return bool((current_app.config.get("MODEL_API_URL") or "").strip())


def predict_leaf_disease(image_path, filename=None, content_type=None):
    api_url = (current_app.config.get("MODEL_API_URL") or "").strip()
    timeout = current_app.config.get("MODEL_API_TIMEOUT_SECONDS", 30)

    if not api_url:
        raise ModelApiError("MODEL_API_URL is not configured.")

    path = Path(image_path)
    if not path.exists():
        raise ModelApiError("Uploaded image could not be found for prediction.")

    try:
        with path.open("rb") as image_file:
            response = _http.post(
                api_url,
                files={
                    "image": (
                        filename or path.name,
                        image_file,
                        content_type or "image/jpeg",
                    )
                },
                timeout=timeout,
            )
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        logger.warning("Model API request timed out after %ss.", timeout)
        raise ModelApiError("The AI model took too long to respond. Please try again.") from exc
    except requests.exceptions.ConnectionError as exc:
        logger.warning("Model API connection failed: %s", exc)
        raise ModelApiError("Could not connect to the AI model service.") from exc
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        logger.warning("Model API returned HTTP %s.", status_code)
        raise ModelApiError("The AI model service returned an error. Please try again.") from exc
    except requests.exceptions.RequestException as exc:
        logger.warning("Model API request failed: %s", exc)
        raise ModelApiError("The AI model service is temporarily unavailable.") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("Model API returned non-JSON response.")
        raise ModelApiError("The AI model service returned an invalid response.") from exc

    return _normalize_prediction_response(payload)


def _normalize_prediction_response(payload):
    if not isinstance(payload, dict):
        raise ModelApiError("The AI model service returned an invalid response.")

    if payload.get("success") is False:
        message = payload.get("error") or payload.get("message") or "Prediction failed."
        raise ModelApiError(str(message))

    class_name = (
        payload.get("disease_class")
        or payload.get("class_name")
        or payload.get("prediction")
        or payload.get("predicted_class")
        or payload.get("label")
    )
    if not class_name:
        raise ModelApiError("The AI model service did not return a disease class.")

    confidence = (
        payload.get("confidence_percent")
        if payload.get("confidence_percent") is not None
        else payload.get("confidence", payload.get("probability", 0))
    )

    return {
        "success": True,
        "disease_class": str(class_name),
        "confidence": confidence,
        "confidence_percent": confidence,
        "raw_response": payload,
        "additional_info": {
            key: value
            for key, value in payload.items()
            if key
            not in {
                "success",
                "disease_class",
                "class_name",
                "prediction",
                "predicted_class",
                "label",
                "confidence",
                "confidence_percent",
                "probability",
            }
        },
    }

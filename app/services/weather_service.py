import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)
TRANSIENT_STATUS_CODES = (502, 503, 504)
MET_LOCATIONFORECAST_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
MET_USER_AGENT = "AgroGuideApp/1.0"


class WeatherServiceError(Exception):
    """User-facing weather service error."""


def _get_json(url: str, params: dict, headers: dict | None = None):
    logger.info("Requesting weather API: %s params=%s", url, params)
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=TRANSIENT_STATUS_CODES,
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    try:
        resp = session.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as exc:
        logger.exception("Weather API request failed: %s params=%s", url, params)
        raise WeatherServiceError(
            "Unable to load weather data right now. Please try again later."
        ) from exc
    except ValueError as exc:
        logger.exception("Weather API returned invalid JSON: %s params=%s", url, params)
        raise WeatherServiceError(
            "Weather data could not be read. Please try again later."
        ) from exc


def geocode_location(query: str):
    params = {"name": query, "count": 5, "language": "en", "format": "json"}
    data = _get_json("https://geocoding-api.open-meteo.com/v1/search", params)
    results = data.get("results") or []
    return results


def fetch_weather(latitude: float, longitude: float):
    params = {"lat": round(float(latitude), 4), "lon": round(float(longitude), 4)}
    data = _get_json(
        MET_LOCATIONFORECAST_URL,
        params,
        headers={"User-Agent": MET_USER_AGENT},
    )

    try:
        forecast = data["properties"]["timeseries"][0]
        details = forecast["data"]["instant"]["details"]
        rain = (
            forecast["data"]
            .get("next_1_hours", {})
            .get("details", {})
            .get("precipitation_amount")
        )
    except (KeyError, IndexError, TypeError) as exc:
        logger.exception("MET Norway response did not include expected forecast fields")
        raise WeatherServiceError(
            "Weather data could not be read. Please try again later."
        ) from exc

    wind_speed_ms = details.get("wind_speed")
    wind_speed_kmh = wind_speed_ms * 3.6 if wind_speed_ms is not None else None

    return {
        "latitude": latitude,
        "longitude": longitude,
        "generationtime_ms": None,
        "utc_offset_seconds": 0,
        "timezone": "auto",
        "timezone_abbreviation": "",
        "elevation": data.get("geometry", {}).get("coordinates", [None, None, None])[2],
        "current_units": {
            "time": "iso8601",
            "temperature_2m": "celsius",
            "relative_humidity_2m": "%",
            "wind_speed_10m": "km/h",
            "rain": "mm",
            "precipitation": "mm",
        },
        "current": {
            "time": forecast.get("time"),
            "temperature_2m": details.get("air_temperature"),
            "relative_humidity_2m": details.get("relative_humidity"),
            "wind_speed_10m": (
                round(wind_speed_kmh, 1) if wind_speed_kmh is not None else None
            ),
            "rain": rain or 0,
            "precipitation": rain or 0,
        },
    }


def generate_farming_advice(temp, humidity, wind, rainfall):
    advice = []
    if temp is not None:
        if temp < 10:
            advice.append("Low temperatures: protect seedlings and delay transplanting.")
        elif temp > 32:
            advice.append("Heat stress risk: irrigate early morning and use mulch.")
        else:
            advice.append("Temperature range is favorable for most field operations.")

    if humidity is not None:
        if humidity > 85:
            advice.append("High humidity favors fungal diseases—improve canopy airflow.")
        elif humidity < 40:
            advice.append("Dry air increases transpiration—monitor soil moisture closely.")

    if rainfall is not None and rainfall > 5:
        advice.append("Recent rainfall: avoid spraying and check drainage in low areas.")

    if wind is not None and wind > 30:
        advice.append("Strong winds: postpone pesticide application.")

    return " ".join(advice) if advice else "Conditions are moderate. Maintain regular scouting."


def generate_disease_risk(temp, humidity, rainfall):
    risk_score = 0
    factors = []

    if humidity is not None and humidity >= 80:
        risk_score += 2
        factors.append("high humidity")
    if temp is not None and 18 <= temp <= 28 and humidity and humidity > 70:
        risk_score += 1
        factors.append("warm moist conditions")
    if rainfall is not None and rainfall > 2:
        risk_score += 2
        factors.append("recent precipitation")

    if risk_score >= 4:
        level = "High"
        msg = "Elevated fungal and bacterial disease risk. Scout daily and consider preventive fungicide where appropriate."
    elif risk_score >= 2:
        level = "Moderate"
        msg = "Some disease pressure possible. Inspect lower canopy leaves and remove infected debris."
    else:
        level = "Low"
        msg = "Disease risk is relatively low. Continue routine monitoring."

    detail = f" Risk factors: {', '.join(factors)}." if factors else ""
    return {"level": level, "message": msg + detail}

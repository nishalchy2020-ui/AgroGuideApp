import requests


def geocode_location(query: str):
    params = {"name": query, "count": 5, "language": "en", "format": "json"}
    resp = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search", params=params, timeout=10
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    return results


def fetch_weather(latitude: float, longitude: float):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
        "daily": "precipitation_sum",
        "timezone": "auto",
    }
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast", params=params, timeout=10
    )
    resp.raise_for_status()
    return resp.json()


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

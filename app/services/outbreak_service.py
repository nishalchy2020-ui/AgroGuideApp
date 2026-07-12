import json
import logging
import math
from datetime import timedelta

from flask import current_app

from app import db
from app.models import ActivityHistory, ScanResult, User, WeatherSearch, utcnow
from app.services.email_service import is_email_transport_configured, send_outbreak_alert_email

logger = logging.getLogger("agroguide.outbreak")


def check_outbreak_for_scan(scan):
    """Check whether a new scan contributes to a local outbreak pattern."""
    window_hours = current_app.config["OUTBREAK_ALERT_WINDOW_HOURS"]
    threshold = current_app.config["OUTBREAK_ALERT_THRESHOLD"]
    radius_km = current_app.config["OUTBREAK_ALERT_RADIUS_KM"]
    since = utcnow() - timedelta(hours=window_hours)

    origin = _latest_location(scan.user_id)
    if not origin:
        logger.info("Skipping outbreak check because user_id=%s has no location.", scan.user_id)
        return []

    scans = (
        ScanResult.query.filter(
            ScanResult.disease_class == scan.disease_class,
            ScanResult.created_at >= since,
        )
        .all()
    )

    affected = []
    for candidate in scans:
        location = _latest_location(candidate.user_id)
        if not location:
            continue
        if _same_district(origin, location) or _distance_km(origin, location) <= radius_km:
            affected.append((candidate, location))

    user_ids = sorted({candidate.user_id for candidate, _ in affected})
    if len(user_ids) < threshold:
        return []
    if not is_email_transport_configured():
        logger.warning("Skipping outbreak email alerts because no email transport is configured.")
        return []

    alert = {
        "disease_class": scan.disease_class,
        "disease_label": scan.disease_label,
        "match_count": len(user_ids),
        "location_name": origin.location_name,
        "window_hours": window_hours,
        "radius_km": radius_km,
    }

    notified = []
    for user_id in user_ids:
        user = db.session.get(User, user_id)
        if not user or not user.is_email_verified:
            continue
        if _already_alerted(user_id, alert):
            continue
        try:
            send_outbreak_alert_email(user, alert)
            _record_alert(user_id, alert)
            notified.append(user_id)
        except Exception:
            logger.exception("Failed to send outbreak alert for user_id=%s", user_id)

    if notified:
        db.session.commit()
    return notified


def _latest_location(user_id):
    return (
        WeatherSearch.query.filter_by(user_id=user_id)
        .order_by(WeatherSearch.created_at.desc())
        .first()
    )


def _same_district(a, b):
    return _district(a.location_name) == _district(b.location_name)


def _district(location_name):
    return (location_name or "").split(",", 1)[0].strip().lower()


def _distance_km(a, b):
    lat1, lon1 = math.radians(a.latitude), math.radians(a.longitude)
    lat2, lon2 = math.radians(b.latitude), math.radians(b.longitude)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    hav = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(hav))


def _alert_key(alert):
    return f"{alert['disease_class']}:{_district(alert['location_name'])}"


def _already_alerted(user_id, alert):
    return (
        ActivityHistory.query.filter_by(user_id=user_id, module="outbreak_alert")
        .filter(ActivityHistory.title == f"Outbreak alert: {alert['disease_label']}")
        .filter(ActivityHistory.summary.contains(_alert_key(alert)))
        .first()
        is not None
    )


def _record_alert(user_id, alert):
    payload = dict(alert)
    payload["alert_key"] = _alert_key(alert)
    db.session.add(
        ActivityHistory(
            user_id=user_id,
            module="outbreak_alert",
            title=f"Outbreak alert: {alert['disease_label']}",
            summary=json.dumps(payload),
        )
    )

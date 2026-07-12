import hashlib
import secrets
from datetime import timedelta

from app.models import utcnow


def generate_token():
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def expires_in(minutes):
    return utcnow() + timedelta(minutes=minutes)


def is_expired(expires_at):
    if not expires_at:
        return True
    return expires_at.replace(tzinfo=None) < utcnow().replace(tzinfo=None)

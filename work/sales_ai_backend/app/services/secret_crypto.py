from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def encrypt_secret(value: str | None) -> str | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    return _fernet().encrypt(cleaned.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError):
        return None


def mask_secret(value: str | None) -> str | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    if len(cleaned) <= 4:
        return "****"
    return f"****{cleaned[-4:]}"


def _fernet() -> Fernet:
    settings = get_settings()
    material = settings.call_provider_config_secret or settings.jwt_secret_key
    key = base64.urlsafe_b64encode(hashlib.sha256(material.encode("utf-8")).digest())
    return Fernet(key)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None

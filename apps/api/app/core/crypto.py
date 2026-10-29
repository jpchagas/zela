"""Secret handling derived from SECRET_KEY: encryption for stored credentials and signed,
expiring tokens for values that round-trip through a browser (OAuth state)."""

import base64
import hashlib
import hmac
import json
import time
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings


class InvalidSignedToken(Exception):
    pass


def _derive(purpose: bytes) -> bytes:
    # One SECRET_KEY, independent keys per purpose.
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=purpose).derive(
        get_settings().secret_key.encode()
    )


@lru_cache
def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_derive(b"zela:credential-encryption")))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Stored credential could not be decrypted") from exc


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(payload: dict[str, Any], *, purpose: str, ttl_seconds: int) -> str:
    body = _b64(json.dumps({**payload, "exp": int(time.time()) + ttl_seconds}).encode())
    mac = hmac.new(_derive(f"zela:sign:{purpose}".encode()), body.encode(), hashlib.sha256)
    return f"{body}.{_b64(mac.digest())}"


def verify(token: str, *, purpose: str) -> dict[str, Any]:
    body, _, mac = token.partition(".")
    expected = hmac.new(_derive(f"zela:sign:{purpose}".encode()), body.encode(), hashlib.sha256)
    try:
        valid = hmac.compare_digest(_unb64(mac), expected.digest())
        payload = json.loads(_unb64(body)) if valid else None
    except (ValueError, json.JSONDecodeError):
        payload = None
    if not isinstance(payload, dict):
        raise InvalidSignedToken("Bad signature")
    if payload.get("exp", 0) < time.time():
        raise InvalidSignedToken("Expired")
    return payload

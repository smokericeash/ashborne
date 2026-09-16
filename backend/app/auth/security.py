from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings, get_settings

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password, password_hash)
    except Exception:
        return False


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_opaque_token(prefix: str, byte_count: int = 32) -> str:
    return f"{prefix}_{secrets.token_urlsafe(byte_count)}"


def _jwt_settings(settings: Settings | None = None) -> Settings:
    return settings or get_settings()


def create_access_token(
    user_id: str,
    role: str,
    settings: Settings | None = None,
    expires_minutes: int | None = None,
) -> tuple[str, int]:
    config = _jwt_settings(settings)
    now = datetime.now(UTC)
    seconds = (expires_minutes or config.session_timeout_minutes) * 60
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(seconds=seconds),
        "iss": config.jwt_issuer,
        "aud": config.jwt_audience,
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, config.secret_key.get_secret_value(), algorithm="HS256"), seconds


def create_refresh_token(
    user_id: str, family_id: str | None = None, settings: Settings | None = None
) -> tuple[str, str, str, datetime]:
    config = _jwt_settings(settings)
    now = datetime.now(UTC)
    jti = secrets.token_urlsafe(24)
    family = family_id or str(__import__("uuid").uuid4())
    expires = now + timedelta(days=config.refresh_token_days)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "family": family,
        "jti": jti,
        "iat": now,
        "nbf": now,
        "exp": expires,
        "iss": config.jwt_issuer,
        "aud": config.jwt_audience,
    }
    encoded = jwt.encode(payload, config.secret_key.get_secret_value(), algorithm="HS256")
    return encoded, jti, family, expires


def decode_token(token: str, expected_type: str, settings: Settings | None = None) -> dict[str, Any]:
    config = _jwt_settings(settings)
    payload = jwt.decode(
        token,
        config.secret_key.get_secret_value(),
        algorithms=["HS256"],
        issuer=config.jwt_issuer,
        audience=config.jwt_audience,
        options={"require": ["exp", "iat", "nbf", "sub", "type", "jti"]},
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("unexpected token type")
    return payload

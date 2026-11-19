"""Password hashing and JWT access tokens (SMPLSGHT-8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings


def hash_password(plain: str) -> str:
    # bcrypt operates on bytes and caps input at 72 bytes.
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(*, user_id: str, tenant_id: str, role: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "tid": tenant_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and validate a token. Raises jwt.PyJWTError on any problem."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])

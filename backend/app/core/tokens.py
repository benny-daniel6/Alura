"""Alura's own session tokens (HS256 JWTs) for email/password and Google sign-in."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import jwt

from app.core.config import settings

ALGORITHM = "HS256"
ISSUER = "alura"
# Development only, so local tokens survive restarts; production must set JWT_SECRET (checked at start-up)
_DEV_SECRET = "alura-development-only-secret-do-not-use-in-production"


def _secret() -> str:
    if settings.JWT_SECRET:
        return settings.JWT_SECRET
    if settings.is_development:
        return _DEV_SECRET
    raise RuntimeError("JWT_SECRET is not configured")


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "iss": ISSUER,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.ACCESS_TOKEN_DAYS)).timestamp()),
    }
    return jwt.encode(claims, _secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[uuid.UUID]:
    """User id from a valid, unexpired Alura token; None for anything else (e.g. a Firebase token)."""
    decoded = decode_access_token_claims(token)
    return decoded[0] if decoded else None


def decode_access_token_claims(token: str) -> Optional[Tuple[uuid.UUID, int]]:
    """(user id, issued-at epoch seconds) from a valid, unexpired Alura token, else None."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=[ALGORITHM], issuer=ISSUER)
    except (jwt.PyJWTError, RuntimeError):
        return None
    if claims.get("typ") != "access":
        return None
    try:
        return uuid.UUID(claims["sub"]), int(claims.get("iat", 0))
    except (KeyError, ValueError, TypeError):
        return None

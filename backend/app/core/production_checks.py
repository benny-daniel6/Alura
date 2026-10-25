"""
Start-up validation for non-development environments: fail fast with a clear message instead of
starting a server that cannot sign users in or store photos.
"""

import os
from typing import List, Tuple

from app.core.config import Settings


def check_production_config(settings: Settings) -> Tuple[List[str], List[str]]:
    """Returns (errors, warnings). Errors must be fixed before the API can serve users."""
    errors: List[str] = []
    warnings: List[str] = []
    if settings.is_development:
        return errors, warnings

    if not (settings.S3_BUCKET_NAME and settings.S3_ACCESS_KEY and settings.S3_SECRET_KEY):
        errors.append("S3 storage is not configured: set S3_BUCKET_NAME, S3_ACCESS_KEY and S3_SECRET_KEY.")

    if len(settings.JWT_SECRET) < 32:
        errors.append(
            "Sign-in is not configured: set JWT_SECRET to a random string of 32+ characters "
            "(python -c \"import secrets; print(secrets.token_urlsafe(48))\")."
        )
    firebase_file = settings.FIREBASE_CREDENTIALS_PATH
    if firebase_file and not os.path.isfile(firebase_file):
        errors.append(f"Firebase credentials file not found: {firebase_file}")
    if not settings.GOOGLE_OAUTH_CLIENT_IDS:
        warnings.append("GOOGLE_OAUTH_CLIENT_IDS is empty: 'Continue with Google' is off (email and guest sign-in work).")

    if settings.DEV_AUTH_BYPASS:
        warnings.append("DEV_AUTH_BYPASS is set but ignored outside development; remove it.")
    if "postgres:postgres@" in settings.DATABASE_URL:
        warnings.append("DATABASE_URL uses the default postgres password; use a strong one.")
    if settings.BACKEND_CORS_ORIGINS == ["*"]:
        warnings.append("BACKEND_CORS_ORIGINS allows any website; list your web origins (the mobile app needs none).")
    if not settings.GEMINI_API_KEY:
        warnings.append("GEMINI_API_KEY is empty: studio photos are off and the stylist uses the rule engine.")
    return errors, warnings

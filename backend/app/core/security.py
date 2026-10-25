import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import firebase_admin
from firebase_admin import auth as firebase_auth, credentials

from app.core.config import settings
from app.core.tokens import decode_access_token_claims
from app.db.session import get_db
from app.models.user import User, UserPreference

logger = logging.getLogger(__name__)

# Firebase Admin SDK only when a service account is configured (optional sign-in provider)
if not firebase_admin._apps and settings.FIREBASE_CREDENTIALS_PATH:
    try:
        firebase_admin.initialize_app(credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH))
    except Exception as e:
        logger.warning(f"Firebase Admin SDK not initialized with live credentials: {e}. DEV_AUTH_BYPASS={settings.DEV_AUTH_BYPASS}")

http_bearer = HTTPBearer(auto_error=False)


async def verify_firebase_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer)) -> Dict[str, Any]:
    """
    Verifies Firebase JWT token from Authorization Bearer header.
    Supports a mock bypass mode for local development and testing when DEV_AUTH_BYPASS=True.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Alura's own session token (email/password or Google sign-in)
    decoded = decode_access_token_claims(token)
    if decoded is not None:
        return {"user_id": decoded[0], "iat": decoded[1]}

    # Development / Testing Bypass Mode (Strictly disallowed in production)
    is_dev_allowed = (settings.ENVIRONMENT == "development" and settings.DEV_AUTH_BYPASS)
    if is_dev_allowed and (token.startswith("dev-token:") or token == "test-token-123"):
        if token.startswith("dev-token:"):
            email = token.replace("dev-token:", "")
            uid = f"mock-firebase-{email.replace('@', '-at-')}"
        else:
            email = "demo@aura-wardrobe.app"
            uid = "mock-firebase-demo"

        return {
            "uid": uid,
            "email": email,
            "name": email.split("@")[0].capitalize(),
            "picture": None,
        }

    if not firebase_admin._apps:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        decoded_token = firebase_auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        logger.info(f"Firebase token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )


LAST_SEEN_RESOLUTION = timedelta(hours=6)


async def touch_last_seen(db: AsyncSession, user: User) -> None:
    """Records activity at most every few hours (guest accounts unused for a month are deleted)."""
    now = datetime.now(timezone.utc)
    last = user.last_seen_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is None or now - last > LAST_SEEN_RESOLUTION:
        user.last_seen_at = now
        await db.commit()


async def get_current_user(
    token_payload: Dict[str, Any] = Depends(verify_firebase_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Retrieves the authenticated user (Alura token), or auto-provisions a Firebase / dev user.
    """
    if "user_id" in token_payload:
        user = (await db.execute(select(User).where(User.id == token_payload["user_id"]))).scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This account no longer exists.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        revoked_before = user.tokens_valid_after
        if revoked_before is not None and revoked_before.tzinfo is None:
            revoked_before = revoked_before.replace(tzinfo=timezone.utc)  # stored as UTC; some drivers drop the zone
        if revoked_before is not None and token_payload.get("iat", 0) < int(revoked_before.timestamp()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="You were signed out. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        await touch_last_seen(db, user)
        return user

    firebase_uid = token_payload.get("uid")
    email = token_payload.get("email")

    if not firebase_uid or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token payload missing uid or email"
        )

    stmt = select(User).where(User.firebase_uid == firebase_uid)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        # Auto-provision user on first authenticated request
        user = User(
            firebase_uid=firebase_uid,
            email=email,
            display_name=token_payload.get("name"),
            avatar_url=token_payload.get("picture"),
        )
        db.add(user)
        await db.flush()

        # Initialize blank user preferences record
        pref = UserPreference(user_id=user.id)
        db.add(pref)
        await db.commit()
        await db.refresh(user)

    return user

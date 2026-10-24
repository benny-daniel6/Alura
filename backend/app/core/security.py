import logging
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import firebase_admin
from firebase_admin import auth as firebase_auth, credentials

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User, UserPreference

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK if credentials provided
if not firebase_admin._apps:
    try:
        if settings.FIREBASE_CREDENTIALS_PATH:
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
        else:
            # Attempt default application credentials
            firebase_admin.initialize_app()
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

    try:
        decoded_token = firebase_auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        logger.error(f"Firebase token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired Firebase ID token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    token_payload: Dict[str, Any] = Depends(verify_firebase_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Retrieves or auto-provisions the authenticated user in PostgreSQL.
    """
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

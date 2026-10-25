import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core import rate_limit
from app.core.passwords import hash_password, verify_password
from app.core.rate_limit import client_ip
from app.core.security import get_current_user
from app.core.tokens import create_access_token
from app.db.session import get_db
from app.models.user import User, UserPreference
from app.schemas.user import (
    AuthSyncRequest,
    AuthTokenResponse,
    ChangePasswordRequest,
    DevTokenResponse,
    GoogleSignInRequest,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/sync", response_model=UserResponse, summary="Sync Firebase User Account")
async def sync_firebase_user(
    body: AuthSyncRequest = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Called after client-side Firebase Auth sign-in/up.
    Ensures user profile exists, optionally updates display name / avatar,
    and returns user state including quiz completion flag.
    """
    if body:
        if body.display_name and body.display_name != current_user.display_name:
            current_user.display_name = body.display_name
        if body.avatar_url and body.avatar_url != current_user.avatar_url:
            current_user.avatar_url = body.avatar_url
        await db.commit()
        await db.refresh(current_user)

    # Check quiz completion
    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    pref_res = await db.execute(stmt)
    pref = pref_res.scalar_one_or_none()

    response = UserResponse.model_validate(current_user)
    response.has_completed_quiz = pref.quiz_completed if pref else False
    return response


@router.post("/dev-token", response_model=DevTokenResponse, summary="Generate Dev Mock Token")
async def generate_dev_token(email: str = "curator@aura-wardrobe.app"):
    """
    Utility endpoint for local dev / testing. Only accessible when DEV_AUTH_BYPASS is active.
    Returns a mock Bearer token for seamless Flutter testing without live Firebase setup.
    """
    if settings.ENVIRONMENT != "development" or not settings.DEV_AUTH_BYPASS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev token generator is disabled in production environments"
        )

    token = f"dev-token:{email}"
    return DevTokenResponse(
        access_token=token,
        token_type="bearer",
        firebase_uid=f"mock-firebase-{email.replace('@', '-at-')}",
        email=email
    )


# ---------------------------------------------------------------------------
# Alura accounts: email/password, Google, guest
# ---------------------------------------------------------------------------

GUEST_EMAIL_DOMAIN = "guest.alura.invalid"  # .invalid can never receive mail (RFC 2606)


# Verifying against a throwaway hash when the email is unknown makes both failures take the same time
_DUMMY_PASSWORD_HASH = hash_password("alura-timing-equaliser")

COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789", "1234567890", "qwerty123", "qwertyuiop",
    "11111111", "00000000", "iloveyou", "abcdefgh", "abc12345", "letmein1", "welcome1", "admin123", "alura123",
    "passw0rd", "sunshine", "princess", "football", "baseball", "monkey123", "dragon123", "trustno1",
}


def check_password_policy(password: str, email: str) -> None:
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS or len(set(password)) < 4:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="That password is too easy to guess. Try a longer phrase.")
    if lowered == email.lower() or lowered == email.split("@")[0].lower():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Your password can't be your email address.")


async def _user_response(db: AsyncSession, user: User) -> UserResponse:
    pref = (await db.execute(select(UserPreference).where(UserPreference.user_id == user.id))).scalar_one_or_none()
    response = UserResponse.model_validate(user)
    response.has_completed_quiz = pref.quiz_completed if pref else False
    return response


async def _token_response(db: AsyncSession, user: User) -> AuthTokenResponse:
    return AuthTokenResponse(access_token=create_access_token(user.id), user=await _user_response(db, user))


async def _create_user(db: AsyncSession, **fields) -> User:
    user = User(firebase_uid=f"local:{uuid.uuid4()}", **fields)
    db.add(user)
    await db.flush()
    db.add(UserPreference(user_id=user.id))
    await db.commit()
    await db.refresh(user)
    return user


async def _email_taken(db: AsyncSession, email: str) -> bool:
    return (await db.execute(select(User.id).where(func.lower(User.email) == email))).first() is not None


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED, summary="Create an account")
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    email = body.email.lower()
    await rate_limit.registrations.enforce(client_ip(request), "Too many accounts created from this network. Try again later.")
    check_password_policy(body.password, email)
    if await _email_taken(db, email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists. Sign in instead.")
    user = await _create_user(
        db,
        email=email,
        display_name=(body.display_name or "").strip() or email.split("@")[0],
        password_hash=hash_password(body.password),
    )
    return await _token_response(db, user)


@router.post("/login", response_model=AuthTokenResponse, summary="Sign in with email and password")
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    email = body.email.lower()
    keys = (f"email:{email}", f"ip:{client_ip(request)}")
    for key in keys:
        if await rate_limit.login_failures.limited(key):
            raise rate_limit.too_many("Too many sign-in attempts. Please wait a few minutes and try again.")
    user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalar_one_or_none()
    # Always run one hash check so an unknown email takes as long as a wrong password
    password_ok = await asyncio.to_thread(
        verify_password, body.password, (user.password_hash if user and user.password_hash else _DUMMY_PASSWORD_HASH)
    )
    if not user or not user.password_hash or not password_ok:
        for key in keys:
            await rate_limit.login_failures.hit(key)
        # Same message whether or not the email exists, so accounts cannot be discovered
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")
    await rate_limit.login_failures.reset(keys[0])
    return await _token_response(db, user)


def _verify_google_id_token(token: str) -> Dict[str, Any]:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    claims = google_id_token.verify_oauth2_token(token, google_requests.Request())
    if claims.get("aud") not in settings.GOOGLE_OAUTH_CLIENT_IDS:
        raise ValueError("token was issued for a different app")
    if not claims.get("email") or not claims.get("email_verified"):
        raise ValueError("Google account email is not verified")
    return claims


@router.post("/google", response_model=AuthTokenResponse, summary="Sign in with Google")
async def google_sign_in(body: GoogleSignInRequest, db: AsyncSession = Depends(get_db)):
    if not settings.GOOGLE_OAUTH_CLIENT_IDS:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google sign-in is not set up on this server.")
    try:
        claims = await asyncio.to_thread(_verify_google_id_token, body.id_token)
    except Exception as e:
        logger.info(f"Google sign-in rejected: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google sign-in failed. Please try again.")

    sub, email = claims["sub"], claims["email"].lower()
    user = (await db.execute(select(User).where(User.google_sub == sub))).scalar_one_or_none()
    if not user:
        # Google has verified this email, so link it to an existing account with the same address
        user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalar_one_or_none()
        if user:
            user.google_sub = sub
            user.avatar_url = user.avatar_url or claims.get("picture")
            await db.commit()
        else:
            user = await _create_user(
                db, email=email, google_sub=sub,
                display_name=claims.get("name") or email.split("@")[0], avatar_url=claims.get("picture"),
            )
    return await _token_response(db, user)


@router.post("/guest", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED, summary="Continue as a guest")
async def guest_sign_in(request: Request, db: AsyncSession = Depends(get_db)):
    """Creates an anonymous account. The app keeps its token; upgrading later keeps all its data."""
    await rate_limit.guest_accounts.enforce(client_ip(request), "Too many guest accounts from this network. Try again later.")
    guest_id = uuid.uuid4().hex[:12]
    user = await _create_user(
        db, email=f"guest-{guest_id}@{GUEST_EMAIL_DOMAIN}", display_name="Guest", is_guest=True,
        last_seen_at=datetime.now(timezone.utc),
    )
    return await _token_response(db, user)



@router.post("/upgrade", response_model=AuthTokenResponse, summary="Turn a guest account into a full account")
async def upgrade_guest(
    body: RegisterRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.is_guest:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This account already has a sign-in.")
    email = body.email.lower()
    check_password_policy(body.password, email)
    if await _email_taken(db, email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
    current_user.email = email
    current_user.password_hash = hash_password(body.password)
    current_user.display_name = (body.display_name or "").strip() or email.split("@")[0]
    current_user.is_guest = False
    await db.commit()
    await db.refresh(current_user)
    return await _token_response(db, current_user)


@router.post("/password", response_model=AuthTokenResponse, summary="Change password (signs out other devices)")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await rate_limit.password_changes.enforce(str(current_user.id))
    if not current_user.password_hash or not await asyncio.to_thread(
        verify_password, body.current_password, current_user.password_hash
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your current password is incorrect.")
    check_password_policy(body.new_password, current_user.email)
    current_user.password_hash = hash_password(body.new_password)
    await _revoke_sessions(db, current_user)
    return await _token_response(db, current_user)


@router.post("/logout-all", summary="Sign out on every device")
async def logout_all(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _revoke_sessions(db, current_user)
    return {"success": True}


async def _revoke_sessions(db: AsyncSession, user: User) -> None:
    # Whole seconds: tokens carry iat in seconds; a token issued after this second stays valid
    user.tokens_valid_after = datetime.now(timezone.utc).replace(microsecond=0)
    await db.commit()
    await db.refresh(user)

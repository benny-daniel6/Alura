from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User, UserPreference
from app.schemas.user import UserResponse, AuthSyncRequest, DevTokenResponse

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

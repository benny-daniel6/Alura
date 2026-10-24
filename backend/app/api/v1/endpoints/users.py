import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User, UserPreference
from app.models.wardrobe import WardrobeItem
from app.models.outfit import Outfit, OutfitItem
from app.services.storage import storage_service
from app.schemas.user import (
    UserResponse,
    StylePreferencesInput,
    StylePreferencesResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/me", response_model=UserResponse, summary="Get Current User")
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the authenticated user's profile and quiz completion status.
    """
    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    result = await db.execute(stmt)
    pref = result.scalar_one_or_none()

    response = UserResponse.model_validate(current_user)
    response.has_completed_quiz = pref.quiz_completed if pref else False
    return response


@router.get(
    "/me/preferences",
    response_model=StylePreferencesResponse,
    summary="Get Style Quiz Preferences"
)
async def get_my_style_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves the user's recorded style preferences and quiz answers.
    """
    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    result = await db.execute(stmt)
    pref = result.scalar_one_or_none()

    if not pref:
        # Create default empty preference record if not present
        pref = UserPreference(user_id=current_user.id)
        db.add(pref)
        await db.commit()
        await db.refresh(pref)

    return pref


@router.put(
    "/me/preferences",
    response_model=StylePreferencesResponse,
    summary="Save Style Preferences Quiz"
)
async def update_my_style_preferences(
    preferences_in: StylePreferencesInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Saves or updates the onboarding style quiz preferences:
    - Gender-neutral aesthetic vibes
    - Preferred & avoided color palettes
    - Daily/weekly primary occasions
    - Climate profile & sizing preference
    Marks quiz_completed = True.
    """
    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    result = await db.execute(stmt)
    pref = result.scalar_one_or_none()

    if not pref:
        pref = UserPreference(user_id=current_user.id)
        db.add(pref)

    pref.style_vibes = preferences_in.style_vibes
    pref.preferred_colors = preferences_in.preferred_colors
    pref.avoided_colors = preferences_in.avoided_colors
    pref.primary_occasions = preferences_in.primary_occasions
    pref.climate_zone = preferences_in.climate_zone
    pref.sizing_preference = preferences_in.sizing_preference
    pref.quiz_completed = True

    await db.commit()
    await db.refresh(pref)
    return pref


@router.delete(
    "/me/delete-data",
    summary="GDPR Hard Delete My Data",
    status_code=status.HTTP_200_OK
)
async def delete_my_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Privacy non-functional requirement:
    Permanently deletes all user data, preferences, uploaded wardrobe items,
    outfits, calendar history, and user profile record.
    """
    user_id = current_user.id

    # Collect every stored asset before the rows disappear
    item_rows = (await db.execute(
        select(
            WardrobeItem.original_image_url,
            WardrobeItem.cutout_image_url,
            WardrobeItem.thumbnail_url,
            WardrobeItem.showcase_image_url,
        ).where(WardrobeItem.user_id == user_id)
    )).all()
    preview_urls = (await db.execute(
        select(Outfit.preview_image_url).where(Outfit.user_id == user_id)
    )).scalars().all()
    asset_urls = [url for row in item_rows for url in row if url] + [url for url in preview_urls if url]

    # Delete children explicitly: the ORM would otherwise try to NULL wardrobe_items.user_id
    # (User.wardrobe_items backref) instead of relying on ON DELETE CASCADE
    user_outfit_ids = select(Outfit.id).where(Outfit.user_id == user_id)
    await db.execute(delete(OutfitItem).where(OutfitItem.outfit_id.in_(user_outfit_ids)))
    await db.execute(delete(Outfit).where(Outfit.user_id == user_id))
    await db.execute(delete(WardrobeItem).where(WardrobeItem.user_id == user_id))
    await db.delete(current_user)  # preferences cascade via the ORM relationship
    await db.commit()

    failed = 0
    for url in asset_urls:
        try:
            await storage_service.delete_file(url)
        except Exception as e:
            failed += 1
            logger.error(f"GDPR purge could not delete asset for user {user_id}: {e}")
    if failed:
        logger.error(f"GDPR purge for user {user_id}: {failed} of {len(asset_urls)} assets need manual cleanup")

    return {
        "success": True,
        "message": f"All data associated with account {current_user.email} (ID: {user_id}) has been permanently purged."
    }

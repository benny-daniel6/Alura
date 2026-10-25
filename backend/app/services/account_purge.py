"""Permanent account deletion (the user's own request, or clean-up of abandoned guest accounts)."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outfit import Outfit, OutfitItem
from app.models.user import User
from app.models.wardrobe import WardrobeItem
from app.services.storage import storage_service

logger = logging.getLogger(__name__)


async def purge_user(db: AsyncSession, user: User) -> None:
    """Deletes the user's rows, then every stored photo; a failed photo delete is logged, never raised."""
    user_id = user.id
    item_rows = (await db.execute(
        select(
            WardrobeItem.original_image_url,
            WardrobeItem.cutout_image_url,
            WardrobeItem.thumbnail_url,
            WardrobeItem.showcase_image_url,
        ).where(WardrobeItem.user_id == user_id)
    )).all()
    preview_urls = (await db.execute(select(Outfit.preview_image_url).where(Outfit.user_id == user_id))).scalars().all()
    asset_urls = [url for row in item_rows for url in row if url] + [url for url in preview_urls if url]

    # Delete children explicitly: the ORM would otherwise try to NULL wardrobe_items.user_id
    # (User.wardrobe_items backref) instead of relying on ON DELETE CASCADE
    user_outfit_ids = select(Outfit.id).where(Outfit.user_id == user_id)
    await db.execute(delete(OutfitItem).where(OutfitItem.outfit_id.in_(user_outfit_ids)))
    await db.execute(delete(Outfit).where(Outfit.user_id == user_id))
    await db.execute(delete(WardrobeItem).where(WardrobeItem.user_id == user_id))
    await db.delete(user)  # preferences cascade via the ORM relationship
    await db.commit()

    failed = 0
    for url in asset_urls:
        try:
            await storage_service.delete_file(url)
        except Exception as e:
            failed += 1
            logger.error(f"Purge could not delete an asset for user {user_id}: {e}")
    if failed:
        logger.error(f"Purge for user {user_id}: {failed} of {len(asset_urls)} assets need manual cleanup")


async def purge_stale_guests(db: AsyncSession, retention_days: int, now: Optional[datetime] = None) -> int:
    """Deletes guest accounts not used for `retention_days`. Returns how many were deleted."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    last_activity = func.coalesce(User.last_seen_at, User.created_at)
    stale = (await db.execute(
        select(User).where(User.is_guest.is_(True), or_(last_activity < cutoff))
    )).scalars().all()
    for user in stale:
        await purge_user(db, user)
    if stale:
        logger.info(f"Deleted {len(stale)} guest account(s) inactive for {retention_days}+ days")
    return len(stale)

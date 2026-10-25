import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, Tuple
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.wardrobe import WardrobeItem, ProcessingStatus, ClothingCategory
from app.services.ml_pipeline import ml_pipeline, MLPipeline
from app.services.storage import storage_service
from app.services.account_purge import purge_stale_guests
from app.services.gemini import GeminiClient, gemini_client
from app.services.garment_studio import create_showcase, tag_garment

logger = logging.getLogger(__name__)


async def startup(ctx: Dict[str, Any]):
    """
    Worker startup hook: load heavy ML models ONCE into memory.
    """
    logger.info("ARQ Worker starting up. Initializing models...")
    pipeline = MLPipeline()
    pipeline.load_models()
    ctx["ml_pipeline"] = pipeline
    logger.info("ARQ Worker ready to accept jobs.")


async def shutdown(ctx: Dict[str, Any]):
    logger.info("ARQ Worker shutting down.")


async def _default_pipeline() -> MLPipeline:
    """Module-level pipeline used outside the ARQ worker (e.g. FastAPI background-task fallback)."""
    await asyncio.to_thread(ml_pipeline.ensure_loaded)
    return ml_pipeline


async def _gemini_studio(gemini: GeminiClient, raw_bytes: bytes) -> Tuple[Optional[bytes], Optional[Dict[str, Any]]]:
    """Product shot + tags from Gemini. Either may be None; failures never fail the job."""
    if settings.GARMENT_IMAGE_PROVIDER != "gemini" or not gemini.enabled:
        return None, None

    showcase_bytes: Optional[bytes] = None
    try:
        showcase_bytes = await create_showcase(raw_bytes, client=gemini)
    except Exception as e:
        logger.warning(f"Gemini studio photo failed, using the original photo: {e}")

    tags: Optional[Dict[str, Any]] = None
    try:
        # Tag from the clean product shot when we have one; it is less ambiguous than a cluttered photo
        tags = await tag_garment(showcase_bytes or raw_bytes, client=gemini)
    except Exception as e:
        logger.warning(f"Gemini tagging failed, using OpenCLIP tags: {e}")
    return showcase_bytes, tags


def _apply_tags(item: WardrobeItem, clip: Dict[str, Any], gemini_tags: Optional[Dict[str, Any]]) -> None:
    tags = dict(clip)
    if gemini_tags:
        tags.update({k: v for k, v in gemini_tags.items() if v})

    if not item.category_user_set:
        try:
            item.category = ClothingCategory(tags.get("category", "top"))
        except ValueError:
            item.category = ClothingCategory.TOP
    if not item.name:
        item.name = gemini_tags.get("name") if gemini_tags and gemini_tags.get("name") else (
            f"{(tags.get('primary_color') or '').capitalize()} "
            f"{tags.get('sub_category') or item.category.value.replace('_', ' ')}".strip()
        )
    item.sub_category = tags.get("sub_category")
    item.primary_color = tags.get("primary_color")
    item.secondary_color = tags.get("secondary_color")
    item.seasons = tags.get("seasons") or ["all_season"]
    if gemini_tags and gemini_tags.get("occasions"):
        item.occasions = gemini_tags["occasions"]


async def process_wardrobe_item(ctx: Dict[str, Any], item_id: str):
    """
    Async ARQ task:
    1. Sets status to 'processing'
    2. Gemini (when configured): white-background product shot + structured tags
    3. rembg background removal (on the product shot when available) for the transparent canvas cutout
    4. OpenCLIP embedding (+ zero-shot tags when Gemini is unavailable)
    5. Saves assets and sets status to 'completed'
    If an error occurs, catches it and sets status to 'failed' with error_message.
    """
    logger.info(f"Starting processing for wardrobe item {item_id}")
    pipeline: MLPipeline = ctx.get("ml_pipeline") or await _default_pipeline()
    gemini: GeminiClient = ctx.get("gemini_client") or gemini_client
    session_factory = ctx.get("session_factory", AsyncSessionLocal)

    async with session_factory() as db:
        stmt = select(WardrobeItem).where(WardrobeItem.id == uuid.UUID(item_id))
        result = await db.execute(stmt)
        item = result.scalar_one_or_none()

        if not item:
            logger.error(f"Wardrobe item {item_id} not found in database.")
            return

        item.status = ProcessingStatus.PROCESSING
        await db.commit()
        await db.refresh(item)

        try:
            raw_bytes = await storage_service.read_file(item.original_image_url)

            showcase_bytes, gemini_tags = await _gemini_studio(gemini, raw_bytes)

            cutout_bytes = await asyncio.to_thread(pipeline.remove_background, showcase_bytes or raw_bytes)
            cutout_url = await storage_service.save_file(cutout_bytes, f"{item.id}_cutout.png", subfolder="cutouts")

            showcase_url = None
            if showcase_bytes:
                showcase_url = await storage_service.save_file(
                    showcase_bytes, f"{item.id}_showcase.png", subfolder="showcase"
                )

            thumb_bytes = await asyncio.to_thread(pipeline.generate_thumbnail, cutout_bytes)
            thumb_url = await storage_service.save_file(thumb_bytes, f"{item.id}_thumb.png", subfolder="thumbnails")

            # OpenCLIP: 512-dim embedding for similarity search, plus fallback zero-shot tags
            analysis = await asyncio.to_thread(pipeline.analyze_garment, cutout_bytes, showcase_bytes or raw_bytes)
            _apply_tags(item, analysis, gemini_tags)

            item.clip_embedding = analysis.get("embedding")
            item.cutout_image_url = cutout_url
            item.showcase_image_url = showcase_url
            item.thumbnail_url = thumb_url
            item.status = ProcessingStatus.COMPLETED
            item.error_message = None

            await db.commit()
            logger.info(
                f"Successfully processed wardrobe item {item_id} "
                f"(studio photo: {'gemini' if showcase_url else 'none'}, tags: {'gemini' if gemini_tags else 'openclip'})"
            )

        except Exception as e:
            # Write failed jobs to status field instead of crashing
            logger.exception(f"Processing failed for wardrobe item {item_id}: {e}")
            item.status = ProcessingStatus.FAILED
            item.error_message = f"ML processing error: {str(e)[:450]}"
            await db.commit()


async def cleanup_stale_guests(ctx: Dict[str, Any]):
    """Daily: delete guest accounts (and their photos) unused for GUEST_RETENTION_DAYS."""
    session_factory = ctx.get("session_factory", AsyncSessionLocal)
    async with session_factory() as db:
        return await purge_stale_guests(db, settings.GUEST_RETENTION_DAYS)


class WorkerSettings:
    functions = [process_wardrobe_item]
    cron_jobs = [cron(cleanup_stale_guests, hour=3, minute=30, run_at_startup=False)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_tries = 3
    # Gemini studio photo + BiRefNet on CPU can take a few minutes; a GPU worker needs far less
    job_timeout = 300
    retry_delay = 5


if __name__ == "__main__":
    # Cross-platform entrypoint: `python -m app.workers.arq_worker`.
    # The `arq` CLI installs Unix signal handlers and references SIGUSR1, neither of which exist on Windows.
    import signal
    import sys

    from arq.worker import create_worker

    logging.basicConfig(level=logging.INFO)
    if sys.platform == "win32":
        if not hasattr(signal, "SIGUSR1"):
            signal.SIGUSR1 = signal.SIGTERM  # arq only uses it as a label in close()
        asyncio.set_event_loop(asyncio.new_event_loop())
        create_worker(WorkerSettings, handle_signals=False).run()
    else:
        create_worker(WorkerSettings).run()

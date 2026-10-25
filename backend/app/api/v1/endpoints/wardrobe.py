import io
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    status,
    Query,
    BackgroundTasks
)
from PIL import Image, ImageOps
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings
from app.core import rate_limit
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.wardrobe import WardrobeItem, ClothingCategory, ProcessingStatus
from app.schemas.wardrobe import (
    WardrobeItemResponse,
    WardrobeUploadResponse,
    WardrobeStatusResponse,
    WardrobeItemUpdate,
    SimilarItemResponse,
    WearRequest,
)
from app.services.storage import storage_service
from app.services.similarity import find_similar_items
from app.workers.arq_worker import process_wardrobe_item

logger = logging.getLogger(__name__)
router = APIRouter()

# Pillow refuses images above this many pixels (DecompressionBombError) instead of exhausting memory.
# 40 MP covers every phone camera; the app sends at most 1024 px anyway.
Image.MAX_IMAGE_PIXELS = 40_000_000

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
FREE_TIER_ITEM_LIMIT = 150


def normalize_upload_image(contents: bytes, content_type: str) -> Tuple[bytes, str]:
    """
    Decodes the upload, bakes EXIF orientation into the pixels and re-encodes it.
    Returns (bytes, file extension). Raises HTTPException for images too small for ML.
    """
    pil_img = Image.open(io.BytesIO(contents))
    pil_img.load()
    pil_img = ImageOps.exif_transpose(pil_img)
    width, height = pil_img.size
    if width < 50 or height < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image resolution is too small (minimum 50x50px required for ML analysis)."
        )

    buf = io.BytesIO()
    if content_type == "image/png":
        pil_img.save(buf, format="PNG")
        return buf.getvalue(), "png"
    if pil_img.mode not in ("RGB", "L"):
        pil_img = pil_img.convert("RGB")
    pil_img.save(buf, format="JPEG", quality=95)
    return buf.getvalue(), "jpg"


async def get_arq_pool():
    if not settings.REDIS_URL:
        return None
    try:
        redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
        redis_settings.conn_timeout = 0.5
        redis_settings.conn_retries = 1
        return await create_pool(redis_settings)
    except Exception:
        return None


@router.post(
    "/items/upload",
    response_model=WardrobeUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload Clothing Image & Enqueue ML Processing"
)
async def upload_wardrobe_item(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    initial_category: Optional[ClothingCategory] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    1. Validates file type/size (max 10MB) and image integrity, applies EXIF transpose.
    2. Enforces the 150-item free-tier limit atomically (row lock on the user).
    3. Saves raw image to storage and creates pending WardrobeItem record.
    4. Enqueues background job to isolated ARQ Redis worker.
    5. Returns immediately with item_id, job_id, and status 'pending'.
    """
    await rate_limit.uploads.enforce(str(current_user.id), "Upload limit reached. Please try again in a while.")

    # 1. Content-type and max file size validation
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image type '{file.content_type}'. Must be JPEG, PNG, or WebP."
        )

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {MAX_IMAGE_SIZE_BYTES // (1024 * 1024)}MB. Please compress client-side."
        )

    # 2. Image integrity & EXIF transpose (phone photos carry orientation in EXIF, not pixels)
    try:
        normalized_contents, ext = normalize_upload_image(contents, file.content_type)
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"Rejected upload from user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corrupt or invalid image format. Please choose a different photo."
        )

    # 3. Atomic freemium check: lock the user row for the rest of this transaction.
    # populate_existing forces a re-read so a count cached by get_current_user (before the lock) is not used.
    user_stmt = (
        select(User)
        .where(User.id == current_user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    locked_user = (await db.execute(user_stmt)).scalar_one()

    if locked_user.role == UserRole.FREE and locked_user.items_count >= FREE_TIER_ITEM_LIMIT:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Free tier wardrobe limit of {FREE_TIER_ITEM_LIMIT} items reached. Upgrade to Alura Luxe for unlimited wardrobe storage."
        )

    # 4. Save normalized raw image in storage
    raw_filename = f"{uuid.uuid4()}_raw.{ext}"
    saved_url = await storage_service.save_file(normalized_contents, raw_filename, subfolder="originals")

    # 5. Create pending database record
    item = WardrobeItem(
        user_id=locked_user.id,
        category=initial_category or ClothingCategory.TOP,
        category_user_set=initial_category is not None,
        original_image_url=saved_url,
        status=ProcessingStatus.PENDING,
    )
    db.add(item)

    # Increment user item count atomically within the locked transaction
    locked_user.items_count = locked_user.items_count + 1
    await db.commit()
    await db.refresh(item)

    job_id = f"job-{item.id}"
    item.job_id = job_id

    # 6. Enqueue ARQ job or background task
    arq_pool = await get_arq_pool()
    if arq_pool:
        try:
            await arq_pool.enqueue_job("process_wardrobe_item", str(item.id))
        except Exception:
            # Fallback to FastAPI background task if Redis connection fails
            background_tasks.add_task(process_wardrobe_item, {}, str(item.id))
        finally:
            await arq_pool.aclose()
    else:
        background_tasks.add_task(process_wardrobe_item, {}, str(item.id))

    await db.commit()

    return WardrobeUploadResponse(
        item_id=item.id,
        job_id=job_id,
        status=ProcessingStatus.PENDING,
        message="Item queued for ML background removal and OpenCLIP tagging"
    )


@router.get(
    "/items/{item_id}/status",
    response_model=WardrobeStatusResponse,
    summary="Poll Processing Status of Wardrobe Item"
)
async def get_item_processing_status(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Polling endpoint used by the mobile app:
    Returns status: 'pending', 'processing', 'completed', or 'failed' (with error_message).
    When completed, returns full item metadata and cutout image URL.
    """
    stmt = select(WardrobeItem).where(
        WardrobeItem.id == item_id,
        WardrobeItem.user_id == current_user.id
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wardrobe item not found."
        )

    return WardrobeStatusResponse(
        item_id=item.id,
        status=item.status,
        job_id=item.job_id,
        error_message=item.error_message,
        item=WardrobeItemResponse.model_validate(item) if item.status == ProcessingStatus.COMPLETED else None
    )


@router.get(
    "/items",
    response_model=List[WardrobeItemResponse],
    summary="List & Filter Wardrobe Items"
)
async def list_wardrobe_items(
    category: Optional[ClothingCategory] = None,
    season: Optional[str] = None,
    is_favorite: Optional[bool] = None,
    search: Optional[str] = Query(None, max_length=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists user's wardrobe items with category, season, and favorite filters.
    """
    query = select(WardrobeItem).where(WardrobeItem.user_id == current_user.id)

    if category:
        query = query.where(WardrobeItem.category == category)
    if is_favorite is not None:
        query = query.where(WardrobeItem.is_favorite == is_favorite)
    if search:
        query = query.where(WardrobeItem.name.ilike(f"%{search}%"))

    query = query.order_by(WardrobeItem.created_at.desc())
    result = await db.execute(query)
    items = result.scalars().all()

    # In-memory filter for JSON seasons array if specified
    if season:
        items = [i for i in items if season in i.seasons or "all_season" in i.seasons]

    return items


@router.get(
    "/items/{item_id}",
    response_model=WardrobeItemResponse,
    summary="Get Single Wardrobe Item"
)
async def get_wardrobe_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WardrobeItem).where(
        WardrobeItem.id == item_id,
        WardrobeItem.user_id == current_user.id
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wardrobe item not found."
        )

    return item


@router.get(
    "/items/{item_id}/similar",
    response_model=List[SimilarItemResponse],
    summary="Find Visually Similar Wardrobe Items (pgvector HNSW)"
)
async def get_similar_items(
    item_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the user's items nearest to this item by CLIP cosine distance.
    """
    stmt = select(WardrobeItem).where(
        WardrobeItem.id == item_id,
        WardrobeItem.user_id == current_user.id
    )
    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wardrobe item not found.")
    if item.clip_embedding is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Item has no embedding yet; wait for processing to complete."
        )

    matches = await find_similar_items(
        db, current_user.id, [float(v) for v in item.clip_embedding], limit=limit, exclude_item_id=item.id
    )
    return [
        SimilarItemResponse(item=WardrobeItemResponse.model_validate(match), distance=distance)
        for match, distance in matches
    ]


@router.post(
    "/items/wear",
    response_model=List[WardrobeItemResponse],
    summary="Log Garments as Worn Today",
)
async def mark_items_worn(
    wear_in: WearRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Increments wear_count and sets last_worn_at for each garment (e.g. "Wear today" on an outfit).
    The AI stylist uses these to rotate the wardrobe instead of repeating recent pieces.
    """
    item_ids = list(dict.fromkeys(wear_in.item_ids))
    items = (await db.execute(
        select(WardrobeItem).where(WardrobeItem.id.in_(item_ids), WardrobeItem.user_id == current_user.id)
    )).scalars().all()
    if len(items) != len(item_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more garments were not found.")

    now = datetime.now(timezone.utc)
    for item in items:
        item.wear_count += 1
        item.last_worn_at = now
    await db.commit()
    for item in items:
        await db.refresh(item)
    return items


@router.patch(
    "/items/{item_id}",
    response_model=WardrobeItemResponse,
    summary="Manually Edit Item Metadata & Tags"
)
async def update_wardrobe_item(
    item_id: uuid.UUID,
    update_data: WardrobeItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Allows user to manually correct or override auto-generated tags:
    category, sub_category, primary_color, seasons, occasions, brand, size, favorite.
    """
    stmt = select(WardrobeItem).where(
        WardrobeItem.id == item_id,
        WardrobeItem.user_id == current_user.id
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wardrobe item not found."
        )

    data = update_data.model_dump(exclude_unset=True)
    for field, val in data.items():
        setattr(item, field, val)
    if "category" in data:
        item.category_user_set = True

    await db.commit()
    await db.refresh(item)
    return item


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Wardrobe Item"
)
async def delete_wardrobe_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WardrobeItem).where(
        WardrobeItem.id == item_id,
        WardrobeItem.user_id == current_user.id
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wardrobe item not found."
        )

    # Delete storage assets
    await storage_service.delete_file(item.original_image_url)
    if item.cutout_image_url:
        await storage_service.delete_file(item.cutout_image_url)
    if item.thumbnail_url:
        await storage_service.delete_file(item.thumbnail_url)
    if item.showcase_image_url:
        await storage_service.delete_file(item.showcase_image_url)

    await db.delete(item)
    locked_user = (await db.execute(
        select(User)
        .where(User.id == current_user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one()
    locked_user.items_count = max(0, locked_user.items_count - 1)
    await db.commit()

    return {"success": True, "message": "Item deleted successfully."}

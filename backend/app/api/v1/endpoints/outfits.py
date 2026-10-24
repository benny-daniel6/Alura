import io
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.wardrobe import WardrobeItem
from app.models.outfit import Outfit, OutfitItem, SeasonType
from app.schemas.outfit import OutfitCreate, OutfitUpdate, OutfitResponse, CanvasState
from app.schemas.wardrobe import WardrobeItemResponse
from app.services.storage import storage_service

router = APIRouter()

MAX_PREVIEW_BYTES = 5 * 1024 * 1024
MAX_PREVIEW_DIMENSION = 4096


def format_outfit_response(outfit: Outfit) -> OutfitResponse:
    resolved_items: List[WardrobeItemResponse] = []
    if outfit.outfit_items:
        # Sort by z_index ascending (back-to-front rendering order)
        sorted_join = sorted(outfit.outfit_items, key=lambda x: x.z_index)
        for join_entry in sorted_join:
            if join_entry.wardrobe_item:
                resolved_items.append(WardrobeItemResponse.model_validate(join_entry.wardrobe_item))

    # Parse canvas state dict into CanvasState schema
    canvas_dict = outfit.canvas_state if isinstance(outfit.canvas_state, dict) else {}
    canvas_schema = CanvasState.model_validate(canvas_dict)

    return OutfitResponse(
        id=outfit.id,
        user_id=outfit.user_id,
        name=outfit.name,
        description=outfit.description,
        occasions=outfit.occasions,
        season=outfit.season,
        canvas_state=canvas_schema,
        preview_image_url=outfit.preview_image_url,
        is_favorite=outfit.is_favorite,
        is_public=outfit.is_public,
        items_count=len(resolved_items),
        items=resolved_items,
        created_at=outfit.created_at,
        updated_at=outfit.updated_at
    )


async def validate_canvas_items(db: AsyncSession, user_id: uuid.UUID, canvas: CanvasState) -> None:
    """Every canvas item must be a distinct garment owned by the user."""
    item_ids = [entry.item_id for entry in canvas.items]
    if len(item_ids) != len(set(item_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Each garment can only be placed on the canvas once."
        )
    if not item_ids:
        return

    stmt = select(WardrobeItem.id).where(
        WardrobeItem.id.in_(item_ids),
        WardrobeItem.user_id == user_id
    )
    valid_ids = set((await db.execute(stmt)).scalars().all())
    missing_ids = set(item_ids) - valid_ids
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Garments not found in your wardrobe: {[str(i) for i in missing_ids]}"
        )


def add_outfit_items(db: AsyncSession, outfit_id: uuid.UUID, canvas: CanvasState) -> None:
    for entry in canvas.items:
        db.add(OutfitItem(outfit_id=outfit_id, item_id=entry.item_id, z_index=entry.z_index))


async def load_outfit(db: AsyncSession, outfit_id: uuid.UUID, user_id: uuid.UUID) -> Outfit:
    query = (
        select(Outfit)
        .where(Outfit.id == outfit_id, Outfit.user_id == user_id)
        .options(
            selectinload(Outfit.outfit_items).selectinload(OutfitItem.wardrobe_item)
        )
        .execution_options(populate_existing=True)
    )
    outfit = (await db.execute(query)).scalar_one_or_none()
    if not outfit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outfit not found.")
    return outfit


@router.post("", response_model=OutfitResponse, status_code=status.HTTP_201_CREATED, summary="Save New Outfit")
async def create_outfit(
    outfit_in: OutfitCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Saves an outfit composed on the drag-and-drop canvas:
    - Validates that all canvas item IDs belong to the current user (and appear once).
    - Saves canvas coordinates (x, y, scale, rotation, z_index) as JSON.
    - Persists join records in outfit_items.
    """
    await validate_canvas_items(db, current_user.id, outfit_in.canvas_state)

    outfit = Outfit(
        user_id=current_user.id,
        name=outfit_in.name,
        description=outfit_in.description,
        occasions=outfit_in.occasions,
        season=outfit_in.season,
        canvas_state=outfit_in.canvas_state.model_dump(mode="json"),
        preview_image_url=outfit_in.preview_image_url,
        is_favorite=outfit_in.is_favorite,
        is_public=outfit_in.is_public,
    )
    db.add(outfit)
    await db.flush()
    add_outfit_items(db, outfit.id, outfit_in.canvas_state)
    await db.commit()

    return format_outfit_response(await load_outfit(db, outfit.id, current_user.id))


@router.get("", response_model=List[OutfitResponse], summary="List User Outfits with Filters")
async def list_outfits(
    occasion: Optional[str] = Query(None, description="Filter by occasion tag"),
    season: Optional[SeasonType] = None,
    is_favorite: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Outfit)
        .where(Outfit.user_id == current_user.id)
        .options(
            selectinload(Outfit.outfit_items).selectinload(OutfitItem.wardrobe_item)
        )
        .order_by(Outfit.created_at.desc())
    )

    if season:
        query = query.where(Outfit.season == season)
    if is_favorite is not None:
        query = query.where(Outfit.is_favorite == is_favorite)

    result = await db.execute(query)
    outfits = result.scalars().all()

    if occasion:
        outfits = [o for o in outfits if occasion in o.occasions]

    return [format_outfit_response(o) for o in outfits]


@router.get("/{outfit_id}", response_model=OutfitResponse, summary="Get Single Outfit")
async def get_outfit(
    outfit_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return format_outfit_response(await load_outfit(db, outfit_id, current_user.id))


@router.patch("/{outfit_id}", response_model=OutfitResponse, summary="Update Outfit")
async def update_outfit(
    outfit_id: uuid.UUID,
    update_data: OutfitUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    outfit = await load_outfit(db, outfit_id, current_user.id)
    patch_dict = update_data.model_dump(exclude_unset=True)

    # Replace canvas state and re-sync the join table if provided
    patch_dict.pop("canvas_state", None)
    if update_data.canvas_state is not None:
        await validate_canvas_items(db, current_user.id, update_data.canvas_state)
        outfit.canvas_state = update_data.canvas_state.model_dump(mode="json")
        await db.execute(delete(OutfitItem).where(OutfitItem.outfit_id == outfit.id))
        add_outfit_items(db, outfit.id, update_data.canvas_state)

    for field, val in patch_dict.items():
        setattr(outfit, field, val)

    await db.commit()
    return format_outfit_response(await load_outfit(db, outfit.id, current_user.id))


@router.post("/{outfit_id}/preview", response_model=OutfitResponse, summary="Upload Canvas Snapshot Preview")
async def upload_outfit_preview(
    outfit_id: uuid.UUID,
    file: UploadFile = File(..., description="PNG snapshot rendered from the canvas RepaintBoundary"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Stores the PNG snapshot of the outfit canvas and sets preview_image_url.
    Replaces (and deletes) any previous preview.
    """
    outfit = await load_outfit(db, outfit_id, current_user.id)

    contents = await file.read()
    if len(contents) > MAX_PREVIEW_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Preview exceeds {MAX_PREVIEW_BYTES // (1024 * 1024)}MB."
        )
    try:
        img = Image.open(io.BytesIO(contents))
        img.verify()
        if img.format != "PNG":
            raise ValueError(f"expected PNG, got {img.format}")
        if max(img.size) > MAX_PREVIEW_DIMENSION:
            raise ValueError(f"preview larger than {MAX_PREVIEW_DIMENSION}px")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid preview image: {e}")

    previous_url = outfit.preview_image_url
    outfit.preview_image_url = await storage_service.save_file(
        contents, f"{outfit.id}_{uuid.uuid4().hex[:8]}.png", subfolder="outfits"
    )
    await db.commit()

    if previous_url:
        try:
            await storage_service.delete_file(previous_url)
        except Exception:
            pass  # stale preview is harmless; never fail the request over cleanup

    return format_outfit_response(await load_outfit(db, outfit.id, current_user.id))


@router.delete("/{outfit_id}", status_code=status.HTTP_200_OK, summary="Delete Outfit")
async def delete_outfit(
    outfit_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Outfit).where(Outfit.id == outfit_id, Outfit.user_id == current_user.id)
    result = await db.execute(stmt)
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outfit not found.")

    preview_url = outfit.preview_image_url
    await db.delete(outfit)
    await db.commit()

    if preview_url:
        try:
            await storage_service.delete_file(preview_url)
        except Exception:
            pass
    return {"success": True, "message": "Outfit removed."}

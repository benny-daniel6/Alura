import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field
from app.models.wardrobe import ClothingCategory, ProcessingStatus


class WardrobeItemBase(BaseModel):
    name: Optional[str] = None
    category: ClothingCategory = ClothingCategory.TOP
    sub_category: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    seasons: List[str] = Field(default_factory=lambda: ["all_season"])
    occasions: List[str] = Field(default_factory=list)
    brand: Optional[str] = None
    size: Optional[str] = None
    is_favorite: bool = False


class WardrobeItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[ClothingCategory] = None
    sub_category: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    seasons: Optional[List[str]] = None
    occasions: Optional[List[str]] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    is_favorite: Optional[bool] = None


class WardrobeItemResponse(WardrobeItemBase):
    id: uuid.UUID
    user_id: uuid.UUID
    original_image_url: str
    cutout_image_url: Optional[str] = None
    showcase_image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    status: ProcessingStatus
    job_id: Optional[str] = None
    error_message: Optional[str] = None
    wear_count: int
    last_worn_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WardrobeUploadResponse(BaseModel):
    item_id: uuid.UUID
    job_id: str
    status: ProcessingStatus = ProcessingStatus.PENDING
    message: str = "Image upload received and enqueued for ML background removal & tagging"


class WardrobeStatusResponse(BaseModel):
    item_id: uuid.UUID
    status: ProcessingStatus
    job_id: Optional[str] = None
    error_message: Optional[str] = None
    item: Optional[WardrobeItemResponse] = None


class SimilarItemResponse(BaseModel):
    item: WardrobeItemResponse
    distance: float = Field(..., description="Cosine distance to the query item (0 = identical)")


class WearRequest(BaseModel):
    item_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=20)

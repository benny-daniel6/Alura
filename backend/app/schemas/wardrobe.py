import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from app.models.wardrobe import ClothingCategory, ProcessingStatus


class WardrobeItemBase(BaseModel):
    name: Optional[str] = Field(default=None, max_length=150)
    category: ClothingCategory = ClothingCategory.TOP
    sub_category: Optional[str] = Field(default=None, max_length=100)
    primary_color: Optional[str] = Field(default=None, max_length=50)
    secondary_color: Optional[str] = Field(default=None, max_length=50)
    seasons: List[str] = Field(default_factory=lambda: ["all_season"])
    occasions: List[str] = Field(default_factory=list)
    brand: Optional[str] = Field(default=None, max_length=100)
    size: Optional[str] = Field(default=None, max_length=30)
    is_favorite: bool = False


class WardrobeItemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=150)
    category: Optional[ClothingCategory] = None
    sub_category: Optional[str] = Field(default=None, max_length=100)
    primary_color: Optional[str] = Field(default=None, max_length=50)
    secondary_color: Optional[str] = Field(default=None, max_length=50)
    seasons: Optional[List[str]] = Field(default=None, max_length=5)
    occasions: Optional[List[str]] = Field(default=None, max_length=10)
    brand: Optional[str] = Field(default=None, max_length=100)
    size: Optional[str] = Field(default=None, max_length=30)
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

    @field_serializer("original_image_url", "cutout_image_url", "showcase_image_url", "thumbnail_url")
    def _signed(self, url: Optional[str]) -> Optional[str]:
        from app.services.storage import storage_service
        return storage_service.client_url(url)


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

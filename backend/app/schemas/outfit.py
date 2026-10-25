import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from app.models.outfit import SeasonType
from app.schemas.wardrobe import WardrobeItemResponse


class CanvasItemState(BaseModel):
    item_id: uuid.UUID
    x: float = Field(default=0.0, description="Horizontal coordinate on canvas")
    y: float = Field(default=0.0, description="Vertical coordinate on canvas")
    scale: float = Field(default=1.0, ge=0.2, le=5.0, description="Scale multiplier")
    rotation: float = Field(default=0.0, description="Rotation angle in radians (clockwise)")
    z_index: int = Field(default=0, description="Layer order: higher z_index renders in front")


class CanvasState(BaseModel):
    items: List[CanvasItemState] = Field(default_factory=list)
    background_color: Optional[str] = Field(default="#141418", description="Canvas background tone")
    canvas_width: Optional[float] = Field(
        default=None, gt=0, description="Logical width the x/y coordinates were authored at (for rescaling)"
    )
    canvas_height: Optional[float] = Field(
        default=None, gt=0, description="Logical height the x/y coordinates were authored at (for rescaling)"
    )


class OutfitBase(BaseModel):
    name: str = Field(..., max_length=150, examples=["Minimalist Autumn Uniform"])
    description: Optional[str] = Field(default=None, max_length=500)
    occasions: List[str] = Field(
        default_factory=list,
        examples=[["office_work", "casual_daily"]],
        description="Occasion tags: office_work, casual_daily, evening_dinner, nightlife, formal_events, athleisure"
    )
    season: SeasonType = SeasonType.ALL_SEASON
    canvas_state: CanvasState = Field(default_factory=CanvasState)
    preview_image_url: Optional[str] = None
    is_favorite: bool = False
    is_public: bool = False


class OutfitCreate(OutfitBase):
    pass


class OutfitUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    occasions: Optional[List[str]] = None
    season: Optional[SeasonType] = None
    canvas_state: Optional[CanvasState] = None
    preview_image_url: Optional[str] = None
    is_favorite: Optional[bool] = None
    is_public: Optional[bool] = None


class OutfitResolvedItem(BaseModel):
    z_index: int
    item: WardrobeItemResponse

    model_config = ConfigDict(from_attributes=True)


class OutfitResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: Optional[str] = None
    occasions: List[str]
    season: SeasonType
    canvas_state: CanvasState
    preview_image_url: Optional[str] = None
    is_favorite: bool
    is_public: bool
    items_count: int
    items: List[WardrobeItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("preview_image_url")
    def _signed(self, url: Optional[str]) -> Optional[str]:
        from app.services.storage import storage_service
        return storage_service.client_url(url)

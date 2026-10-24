import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
    JSON,
    Enum as SQLEnum,
    func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.models.wardrobe import ClothingCategory, WardrobeItem
import enum


class SeasonType(str, enum.Enum):
    SPRING = "spring"
    SUMMER = "summer"
    FALL = "fall"
    WINTER = "winter"
    ALL_SEASON = "all_season"


class Outfit(Base):
    __tablename__ = "outfits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    occasions: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    season: Mapped[SeasonType] = mapped_column(
        SQLEnum(SeasonType, name="season_type", values_callable=lambda obj: [e.value for e in obj]),
        default=SeasonType.ALL_SEASON,
        nullable=False
    )
    # Stored canvas coordinates: {"items": [{"item_id": "...", "x": 120.0, "y": 80.0, "scale": 1.0, "rotation": 0.0, "z_index": 1}]}
    canvas_state: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    preview_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    outfit_items: Mapped[List["OutfitItem"]] = relationship(
        "OutfitItem",
        back_populates="outfit",
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class OutfitItem(Base):
    __tablename__ = "outfit_items"

    outfit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outfits.id", ondelete="CASCADE"),
        primary_key=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wardrobe_items.id", ondelete="CASCADE"),
        primary_key=True
    )
    z_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    outfit: Mapped["Outfit"] = relationship("Outfit", back_populates="outfit_items")
    wardrobe_item: Mapped["WardrobeItem"] = relationship("WardrobeItem", lazy="selectin")

import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
    JSON,
    Index,
    Enum as SQLEnum,
    func,
    false,
)
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
import enum

EMBEDDING_DIM = 512


class ClothingCategory(str, enum.Enum):
    TOP = "top"
    BOTTOM = "bottom"
    OUTERWEAR = "outerwear"
    DRESS = "dress"
    FOOTWEAR = "footwear"
    BAG = "bag"
    ACCESSORY = "accessory"
    HEADWEAR = "headwear"
    ONE_PIECE = "one_piece"


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class WardrobeItem(Base):
    __tablename__ = "wardrobe_items"
    __table_args__ = (
        # HNSW index for cosine-distance nearest-neighbour search (pgvector `<=>` operator)
        Index(
            "ix_wardrobe_items_clip_embedding_hnsw",
            "clip_embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"clip_embedding": "vector_cosine_ops"},
        ),
    )

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
    name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    category: Mapped[ClothingCategory] = mapped_column(
        SQLEnum(ClothingCategory, name="clothing_category", values_callable=lambda obj: [e.value for e in obj]),
        default=ClothingCategory.TOP,
        nullable=False,
        index=True
    )
    # True when the user picked/edited the category, so AI tagging must not overwrite it
    category_user_set: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    sub_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    primary_color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    secondary_color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    seasons: Mapped[List[str]] = mapped_column(JSON, default=lambda: ["all_season"], nullable=False)
    occasions: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    size: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Assets
    original_image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    cutout_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # White-background e-commerce style product shot (Gemini); None when the local pipeline was used
    showcase_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # 512-dim OpenCLIP ViT-B/32 embedding: pgvector on PostgreSQL, JSON list on SQLite (unit tests)
    clip_embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(EMBEDDING_DIM).with_variant(JSON(), "sqlite"),
        nullable=True,
    )

    # Job tracking
    status: Mapped[ProcessingStatus] = mapped_column(
        SQLEnum(ProcessingStatus, name="processing_status", values_callable=lambda obj: [e.value for e in obj]),
        default=ProcessingStatus.PENDING,
        nullable=False,
        index=True
    )
    job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Usage metrics
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wear_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_worn_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

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

    # Relationship to user
    user = relationship("User", backref="wardrobe_items")

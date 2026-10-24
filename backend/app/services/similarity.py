import math
import uuid
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wardrobe import WardrobeItem, ProcessingStatus


def _cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 1.0 - dot / norm if norm else 1.0


async def find_similar_items(
    db: AsyncSession,
    user_id: uuid.UUID,
    embedding: Sequence[float],
    limit: int = 10,
    exclude_item_id: Optional[uuid.UUID] = None,
) -> List[Tuple[WardrobeItem, float]]:
    """
    Nearest wardrobe items by cosine distance on the CLIP embedding.
    On PostgreSQL this compiles to `ORDER BY clip_embedding <=> :vec LIMIT n`, which is
    served by the HNSW (vector_cosine_ops) index. SQLite (unit tests) computes it in Python.
    """
    filters = [
        WardrobeItem.user_id == user_id,
        WardrobeItem.status == ProcessingStatus.COMPLETED,
        WardrobeItem.clip_embedding.isnot(None),
    ]
    if exclude_item_id is not None:
        filters.append(WardrobeItem.id != exclude_item_id)

    if db.get_bind().dialect.name == "postgresql":
        distance = WardrobeItem.clip_embedding.cosine_distance(list(embedding)).label("distance")
        stmt = select(WardrobeItem, distance).where(*filters).order_by(distance).limit(limit)
        rows = (await db.execute(stmt)).all()
        return [(row[0], float(row[1])) for row in rows]

    items = (await db.execute(select(WardrobeItem).where(*filters))).scalars().all()
    scored = [(item, _cosine_distance(embedding, item.clip_embedding)) for item in items]
    scored.sort(key=lambda pair: pair[1])
    return scored[:limit]

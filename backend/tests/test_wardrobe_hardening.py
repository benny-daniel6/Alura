import io
import uuid

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

import app.api.v1.endpoints.wardrobe as wardrobe_endpoint
from app.models.user import User, UserRole
from app.models.wardrobe import WardrobeItem, ClothingCategory, ProcessingStatus
from app.services.ml_pipeline import MLPipeline
from app.services.storage import storage_service

EXIF_ORIENTATION_TAG = 0x0112


def jpeg_with_orientation(size=(200, 100), orientation=6) -> bytes:
    """Wide image whose EXIF says 'rotate 90° CW to display' (how phones store portrait shots)."""
    img = Image.new("RGB", size, "white")
    img.paste((200, 0, 0), (0, 0, 20, 20))  # red marker in the stored top-left corner
    exif = Image.Exif()
    exif[EXIF_ORIENTATION_TAG] = orientation
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes(), quality=95)
    return buf.getvalue()


def plain_jpeg(size=(120, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "navy").save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def isolated_upload(monkeypatch, tmp_path):
    """Keeps uploads on tmp disk and skips enqueuing ML jobs; these tests cover the upload transaction."""
    async def no_pool():
        return None

    async def no_processing(ctx, item_id):
        return None

    monkeypatch.setattr(wardrobe_endpoint, "get_arq_pool", no_pool)
    monkeypatch.setattr(wardrobe_endpoint, "process_wardrobe_item", no_processing)
    monkeypatch.setattr(storage_service, "local_dir", tmp_path)
    return tmp_path


async def sync_user(client: AsyncClient, email: str) -> dict:
    headers = {"Authorization": f"Bearer dev-token:{email}"}
    resp = await client.post("/api/v1/auth/sync", headers=headers)
    return {"headers": headers, "id": uuid.UUID(resp.json()["id"])}


# ---------- EXIF transpose ----------

@pytest.mark.asyncio
async def test_upload_applies_exif_transpose_before_storing(async_client: AsyncClient, db_session, isolated_upload):
    user = await sync_user(async_client, "exif@aura.app")
    resp = await async_client.post(
        "/api/v1/wardrobe/items/upload",
        headers=user["headers"],
        files={"file": ("portrait.jpg", jpeg_with_orientation(), "image/jpeg")},
    )
    assert resp.status_code == 202

    item = (await db_session.execute(
        select(WardrobeItem).where(WardrobeItem.id == uuid.UUID(resp.json()["item_id"]))
    )).scalar_one()
    stored = Image.open(io.BytesIO(await storage_service.read_file(item.original_image_url)))

    assert stored.size == (100, 200)  # rotated to portrait
    assert stored.getexif().get(EXIF_ORIENTATION_TAG) in (None, 1)
    # Orientation 6 moves the stored top-left corner to the displayed top-right
    r, g, b = stored.convert("RGB").getpixel((95, 5))
    assert r > 150 and g < 80 and b < 80


def test_pipeline_applies_exif_transpose(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    pipeline = MLPipeline()  # unloaded: exercises the dev fallback path, which shares the transpose step
    cutout = Image.open(io.BytesIO(pipeline.remove_background(jpeg_with_orientation())))
    assert cutout.size == (100, 200)
    thumb = Image.open(io.BytesIO(pipeline.generate_thumbnail(jpeg_with_orientation())))
    assert thumb.size[1] > thumb.size[0]


# ---------- 150-item quota ----------

async def set_user_state(db_session, user_id, items_count, role=UserRole.FREE):
    user = (await db_session.execute(select(User).where(User.id == user_id))).scalar_one()
    user.items_count = items_count
    user.role = role
    await db_session.commit()


async def current_count(db_session, user_id) -> int:
    user = (await db_session.execute(
        select(User).where(User.id == user_id).execution_options(populate_existing=True)
    )).scalar_one()
    return user.items_count


@pytest.mark.asyncio
async def test_quota_allows_the_150th_item_then_blocks(async_client: AsyncClient, db_session, isolated_upload):
    user = await sync_user(async_client, "quota@aura.app")
    await set_user_state(db_session, user["id"], 149)

    ok = await async_client.post(
        "/api/v1/wardrobe/items/upload", headers=user["headers"],
        files={"file": ("a.jpg", plain_jpeg(), "image/jpeg")},
    )
    assert ok.status_code == 202
    assert await current_count(db_session, user["id"]) == 150

    blocked = await async_client.post(
        "/api/v1/wardrobe/items/upload", headers=user["headers"],
        files={"file": ("b.jpg", plain_jpeg(), "image/jpeg")},
    )
    assert blocked.status_code == 403
    assert "150" in blocked.json()["detail"]
    assert await current_count(db_session, user["id"]) == 150
    assert list(isolated_upload.rglob("*.jpg")).__len__() == 1  # rejected upload stored nothing


@pytest.mark.asyncio
async def test_invalid_upload_does_not_consume_quota(async_client: AsyncClient, db_session, isolated_upload):
    user = await sync_user(async_client, "invalid@aura.app")
    await set_user_state(db_session, user["id"], 10)
    resp = await async_client.post(
        "/api/v1/wardrobe/items/upload", headers=user["headers"],
        files={"file": ("bad.jpg", b"not an image", "image/jpeg")},
    )
    assert resp.status_code == 400
    assert await current_count(db_session, user["id"]) == 10


@pytest.mark.asyncio
async def test_premium_users_are_not_capped(async_client: AsyncClient, db_session, isolated_upload):
    user = await sync_user(async_client, "luxe@aura.app")
    await set_user_state(db_session, user["id"], 400, role=UserRole.PREMIUM)
    resp = await async_client.post(
        "/api/v1/wardrobe/items/upload", headers=user["headers"],
        files={"file": ("a.jpg", plain_jpeg(), "image/jpeg")},
    )
    assert resp.status_code == 202
    assert await current_count(db_session, user["id"]) == 401


@pytest.mark.asyncio
async def test_delete_releases_quota_slot(async_client: AsyncClient, db_session, isolated_upload):
    user = await sync_user(async_client, "release@aura.app")
    await set_user_state(db_session, user["id"], 149)
    resp = await async_client.post(
        "/api/v1/wardrobe/items/upload", headers=user["headers"],
        files={"file": ("a.jpg", plain_jpeg(), "image/jpeg")},
    )
    item_id = resp.json()["item_id"]
    assert (await async_client.delete(f"/api/v1/wardrobe/items/{item_id}", headers=user["headers"])).status_code == 200
    assert await current_count(db_session, user["id"]) == 149


# ---------- Similarity search ----------

def unit_vector(*components) -> list:
    vec = [0.0] * 512
    for i, value in enumerate(components):
        vec[i] = value
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec]


@pytest.mark.asyncio
async def test_similar_items_ordered_by_cosine_distance(async_client: AsyncClient, db_session):
    user = await sync_user(async_client, "similar@aura.app")
    other = await sync_user(async_client, "someone-else@aura.app")

    def make(owner, name, vec, status=ProcessingStatus.COMPLETED):
        return WardrobeItem(
            user_id=owner, name=name, category=ClothingCategory.TOP,
            original_image_url=f"/static/originals/{name}.jpg", status=status, clip_embedding=vec,
        )

    query = make(user["id"], "query", unit_vector(1, 0))
    near = make(user["id"], "near", unit_vector(1, 0.1))
    far = make(user["id"], "far", unit_vector(0, 1))
    pending = make(user["id"], "pending", None, status=ProcessingStatus.PENDING)
    foreign = make(other["id"], "foreign", unit_vector(1, 0))
    db_session.add_all([query, near, far, pending, foreign])
    await db_session.commit()

    resp = await async_client.get(f"/api/v1/wardrobe/items/{query.id}/similar", headers=user["headers"])
    assert resp.status_code == 200
    results = resp.json()
    assert [r["item"]["name"] for r in results] == ["near", "far"]
    assert results[0]["distance"] < 0.01 < results[1]["distance"]

    no_embedding = await async_client.get(f"/api/v1/wardrobe/items/{pending.id}/similar", headers=user["headers"])
    assert no_embedding.status_code == 409
    not_mine = await async_client.get(f"/api/v1/wardrobe/items/{foreign.id}/similar", headers=user["headers"])
    assert not_mine.status_code == 404

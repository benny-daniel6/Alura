import io
import uuid
import pytest
from httpx import AsyncClient
from PIL import Image

from app.models.wardrobe import ClothingCategory, ProcessingStatus
from app.workers.arq_worker import process_wardrobe_item


def create_dummy_image(color="blue", size=(200, 200)) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_wardrobe_upload_validation(async_client: AsyncClient):
    headers = {"Authorization": "Bearer dev-token:curator@aura-wardrobe.app"}

    # 1. Invalid mime type rejection
    resp = await async_client.post(
        "/api/v1/wardrobe/items/upload",
        headers=headers,
        files={"file": ("notes.txt", b"plain text", "text/plain")}
    )
    assert resp.status_code == 400
    assert "Unsupported image type" in resp.json()["detail"]

    # 2. Corrupt image file rejection
    resp2 = await async_client.post(
        "/api/v1/wardrobe/items/upload",
        headers=headers,
        files={"file": ("corrupt.jpg", b"fake binary data not an image", "image/jpeg")}
    )
    assert resp2.status_code == 400
    assert "Corrupt or invalid image" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_wardrobe_upload_and_polling_status(async_client: AsyncClient, monkeypatch):
    import app.api.v1.endpoints.wardrobe as wardrobe_endpoint
    async def mock_pool():
        return None
    monkeypatch.setattr(wardrobe_endpoint, "get_arq_pool", mock_pool)

    headers = {"Authorization": "Bearer dev-token:fashionista@aura-wardrobe.app"}

    # Sync user first
    await async_client.post("/api/v1/auth/sync", headers=headers)

    # 1. Upload valid garment photo
    img_bytes = create_dummy_image(color="navy", size=(300, 400))
    upload_resp = await async_client.post(
        "/api/v1/wardrobe/items/upload",
        headers=headers,
        files={"file": ("navy_jacket.jpg", img_bytes, "image/jpeg")},
        data={"initial_category": "outerwear"}
    )
    assert upload_resp.status_code == 202
    upload_data = upload_resp.json()
    assert "item_id" in upload_data
    assert "job_id" in upload_data
    item_id = upload_data["item_id"]
    assert upload_data["status"] == "pending"

    # 2. Poll status endpoint immediately
    status_resp = await async_client.get(
        f"/api/v1/wardrobe/items/{item_id}/status",
        headers=headers
    )
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["item_id"] == item_id
    assert status_data["status"] in ["pending", "processing", "completed"]

    # 3. Trigger worker task directly to simulate isolated ARQ processing
    # Unloaded pipeline -> development-only heuristic fallback (real models are covered by the Postgres test)
    from tests.conftest import TestingSessionLocal
    from app.services.ml_pipeline import MLPipeline
    await process_wardrobe_item({"session_factory": TestingSessionLocal, "ml_pipeline": MLPipeline()}, item_id)

    # 4. Verify polling endpoint returns 'completed' with cutout and tags
    completed_status = await async_client.get(
        f"/api/v1/wardrobe/items/{item_id}/status",
        headers=headers
    )
    assert completed_status.status_code == 200
    comp_data = completed_status.json()
    assert comp_data["status"] == "completed"
    assert comp_data["item"] is not None
    assert comp_data["item"]["cutout_image_url"] is not None
    assert comp_data["item"]["thumbnail_url"] is not None

    # 5. List items with category filter
    list_resp = await async_client.get(
        "/api/v1/wardrobe/items",
        headers=headers
    )
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) >= 1
    found = [i for i in items if i["id"] == item_id]
    assert len(found) == 1

    # 6. Manual edit tags (Patch)
    patch_resp = await async_client.patch(
        f"/api/v1/wardrobe/items/{item_id}",
        headers=headers,
        json={
            "name": "Tailored Navy Wool Blazer",
            "category": "outerwear",
            "brand": "Acne Studios",
            "size": "M",
            "is_favorite": True
        }
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["name"] == "Tailored Navy Wool Blazer"
    assert patched["brand"] == "Acne Studios"
    assert patched["is_favorite"] is True

    # 7. Delete item
    del_resp = await async_client.delete(
        f"/api/v1/wardrobe/items/{item_id}",
        headers=headers
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # Verify 404 after deletion
    after_del = await async_client.get(
        f"/api/v1/wardrobe/items/{item_id}/status",
        headers=headers
    )
    assert after_del.status_code == 404


@pytest.mark.asyncio
async def test_failed_job_writes_to_status_field_instead_of_crashing(async_client: AsyncClient, monkeypatch):
    import app.api.v1.endpoints.wardrobe as wardrobe_endpoint
    async def mock_pool():
        return None
    monkeypatch.setattr(wardrobe_endpoint, "get_arq_pool", mock_pool)

    headers = {"Authorization": "Bearer dev-token:resilience@aura-wardrobe.app"}
    await async_client.post("/api/v1/auth/sync", headers=headers)

    # 1. Upload valid garment
    img_bytes = create_dummy_image(color="red", size=(200, 200))
    upload_resp = await async_client.post(
        "/api/v1/wardrobe/items/upload",
        headers=headers,
        files={"file": ("red_shirt.jpg", img_bytes, "image/jpeg")},
    )
    assert upload_resp.status_code == 202
    item_id = upload_resp.json()["item_id"]

    # 2. Simulate ML pipeline throwing an unexpected error
    from app.services.ml_pipeline import MLPipeline
    class CrashingPipeline(MLPipeline):
        def remove_background(self, image_bytes: bytes) -> bytes:
            raise RuntimeError("CUDA Out Of Memory / ONNX Runtime failure simulation")

    from tests.conftest import TestingSessionLocal
    # Run worker with crashing pipeline: must NOT crash the worker process
    await process_wardrobe_item(
        {"session_factory": TestingSessionLocal, "ml_pipeline": CrashingPipeline()},
        item_id
    )

    # 3. Poll status endpoint: verify failed status and error message written to DB
    status_resp = await async_client.get(
        f"/api/v1/wardrobe/items/{item_id}/status",
        headers=headers
    )
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "failed"
    assert "CUDA Out Of Memory" in status_data["error_message"]
    assert status_data["item"] is None

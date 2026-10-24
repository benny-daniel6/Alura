"""
Gemini garment studio: REST client parsing, and the worker's Gemini path + local fallback.
The Gemini API is mocked with httpx.MockTransport; no network calls are made.
"""

import base64
import io
import json

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app.models.wardrobe import ClothingCategory, ProcessingStatus, WardrobeItem
from app.services.gemini import GeminiClient, GeminiError
from app.services.ml_pipeline import MLPipeline
from app.workers.arq_worker import process_wardrobe_item

HEADERS = {"Authorization": "Bearer dev-token:studio@aura.app"}


def _jpeg(color=(200, 120, 140), size=(300, 400)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def _png_b64(color=(255, 255, 255), size=(256, 256)) -> str:
    buf = io.BytesIO()
    img = Image.new("RGB", size, color)
    img.paste((200, 120, 140), (64, 64, 192, 192))  # garment on white
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


TAGS = {
    "name": "Pink camo-print polo shirt",
    "category": "top",
    "sub_category": "polo shirt",
    "primary_color": "pink",
    "secondary_color": "white",
    "pattern": "camo",
    "seasons": ["spring", "summer", "bogus"],
    "occasions": ["casual_daily", "not_an_occasion"],
}


def gemini_transport(calls, image_status=200, text_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append((request.url.path, request.headers.get("x-goog-api-key"), body))
        if "flash-image" in request.url.path:
            if image_status != 200:
                return httpx.Response(image_status, json={"error": {"message": "quota"}})
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"text": "Here is your product photo."},
                {"inlineData": {"mimeType": "image/png", "data": _png_b64()}},
            ]}}]})
        if text_status != 200:
            return httpx.Response(text_status, json={"error": {"message": "boom"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(TAGS)}]}}]})

    return httpx.MockTransport(handler)


def make_client(calls, **kw) -> GeminiClient:
    return GeminiClient(
        api_key="test-key",
        text_model="gemini-2.5-flash",
        image_model="gemini-2.5-flash-image",
        transport=gemini_transport(calls, **kw),
    )


@pytest.mark.asyncio
async def test_client_sends_key_header_and_parses_json_and_images():
    calls = []
    client = make_client(calls)

    data = await client.generate_json("sys", "prompt", {"type": "OBJECT"})
    assert data["name"] == TAGS["name"]
    path, key, body = calls[0]
    assert path.endswith("/models/gemini-2.5-flash:generateContent")
    assert key == "test-key"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "key=" not in str(calls[0])  # key goes in the header, never the URL

    img = await client.edit_image(_jpeg(), "image/jpeg", "make it a product shot")
    assert Image.open(io.BytesIO(img)).size == (256, 256)


@pytest.mark.asyncio
async def test_client_errors_are_gemini_errors():
    with pytest.raises(GeminiError):
        await GeminiClient(api_key="").generate_json("s", "p", {})
    calls = []
    with pytest.raises(GeminiError, match="HTTP 429"):
        await make_client(calls, image_status=429).edit_image(_jpeg(), "image/jpeg", "x")

    no_image = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "I can't"}]}}]})
    )
    with pytest.raises(GeminiError, match="no image"):
        await GeminiClient(api_key="k", transport=no_image).edit_image(_jpeg(), "image/jpeg", "x")

    blocked = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})
    )
    with pytest.raises(GeminiError, match="SAFETY"):
        await GeminiClient(api_key="k", transport=blocked).generate_json("s", "p", {})


async def _upload(async_client, monkeypatch, initial_category=None) -> str:
    import app.api.v1.endpoints.wardrobe as wardrobe_endpoint

    async def no_pool():
        return None

    monkeypatch.setattr(wardrobe_endpoint, "get_arq_pool", no_pool)
    # Without a pool the endpoint processes inline; make that a no-op so the test drives the worker itself
    async def skip_inline(*args, **kwargs):
        return None

    monkeypatch.setattr(wardrobe_endpoint, "process_wardrobe_item", skip_inline)
    await async_client.post("/api/v1/auth/sync", headers=HEADERS)
    data = {"initial_category": initial_category} if initial_category else {}
    resp = await async_client.post(
        "/api/v1/wardrobe/items/upload",
        headers=HEADERS,
        files={"file": ("polo.jpg", _jpeg(), "image/jpeg")},
        data=data,
    )
    assert resp.status_code == 202, resp.text
    return resp.json()["item_id"]


async def _run_worker(item_id, gemini):
    from tests.conftest import TestingSessionLocal

    await process_wardrobe_item(
        {"session_factory": TestingSessionLocal, "ml_pipeline": MLPipeline(), "gemini_client": gemini}, item_id
    )


@pytest.mark.asyncio
async def test_worker_uses_gemini_product_shot_and_tags(async_client, db_session, monkeypatch):
    item_id = await _upload(async_client, monkeypatch)
    calls = []
    await _run_worker(item_id, make_client(calls))

    resp = await async_client.get(f"/api/v1/wardrobe/items/{item_id}/status", headers=HEADERS)
    item = resp.json()["item"]
    assert item["status"] == "completed"
    assert item["showcase_image_url"].endswith(f"{item_id}_showcase.png")
    assert item["name"] == "Pink camo-print polo shirt"
    assert item["sub_category"] == "camo polo shirt"
    assert item["primary_color"] == "pink" and item["secondary_color"] == "white"
    assert item["seasons"] == ["spring", "summer"]  # unknown values dropped
    assert item["occasions"] == ["casual_daily"]
    assert item["cutout_image_url"] and item["thumbnail_url"]

    image_calls = [c for c in calls if "flash-image" in c[0]]
    tag_calls = [c for c in calls if "flash-image" not in c[0]]
    assert len(image_calls) == 1 and len(tag_calls) == 1
    # Tagging runs on the clean product shot, not the original photo
    sent = tag_calls[0][2]["contents"][0]["parts"][0]["inlineData"]["data"]
    tagged = Image.open(io.BytesIO(base64.b64decode(sent)))
    assert tagged.size == (256, 256)

    # Stored showcase image is a real PNG on disk
    from app.services.storage import storage_service
    stored = await storage_service.read_file(item["showcase_image_url"])
    assert Image.open(io.BytesIO(stored)).format == "PNG"


@pytest.mark.asyncio
async def test_worker_respects_user_category(async_client, db_session, monkeypatch):
    item_id = await _upload(async_client, monkeypatch, initial_category="outerwear")
    await _run_worker(item_id, make_client([]))
    item = (await async_client.get(f"/api/v1/wardrobe/items/{item_id}/status", headers=HEADERS)).json()["item"]
    assert item["category"] == "outerwear"  # Gemini said "top"; the user's choice wins
    assert item["name"] == "Pink camo-print polo shirt"


@pytest.mark.asyncio
async def test_worker_falls_back_to_local_pipeline_when_gemini_fails(async_client, db_session, monkeypatch):
    item_id = await _upload(async_client, monkeypatch)
    calls = []
    await _run_worker(item_id, make_client(calls, image_status=500, text_status=500))

    item = (await async_client.get(f"/api/v1/wardrobe/items/{item_id}/status", headers=HEADERS)).json()["item"]
    assert item["status"] == "completed"
    assert item["showcase_image_url"] is None
    assert item["cutout_image_url"]
    assert len(calls) == 2  # tried both, then fell back


@pytest.mark.asyncio
async def test_worker_skips_gemini_without_key_or_when_local(async_client, db_session, monkeypatch):
    item_id = await _upload(async_client, monkeypatch)
    calls = []
    await _run_worker(item_id, GeminiClient(api_key="", transport=gemini_transport(calls)))
    assert calls == []

    from app.core.config import settings
    monkeypatch.setattr(settings, "GARMENT_IMAGE_PROVIDER", "local")
    item_id2 = await _upload(async_client, monkeypatch)
    await _run_worker(item_id2, make_client(calls))
    assert calls == []
    rows = (await db_session.execute(select(WardrobeItem))).scalars().all()
    assert all(r.status == ProcessingStatus.COMPLETED and r.showcase_image_url is None for r in rows)


def test_clean_cutout_alpha_removes_stray_blobs_but_keeps_pairs():
    import numpy as np
    from app.services.ml_pipeline import clean_cutout_alpha

    rgba = np.zeros((200, 200, 4), dtype=np.uint8)
    rgba[20:120, 20:90, 3] = 255     # shoe 1
    rgba[20:120, 110:180, 3] = 255   # shoe 2 (same size: must survive)
    rgba[180:184, 10:14, 3] = 255    # speck of bedding (must go)
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG")

    out = np.array(Image.open(io.BytesIO(clean_cutout_alpha(buf.getvalue()))))
    assert out[60, 50, 3] == 255 and out[60, 140, 3] == 255
    assert out[182, 12, 3] == 0

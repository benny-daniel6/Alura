import uuid
import pytest
from httpx import AsyncClient

from app.models.wardrobe import ClothingCategory, ProcessingStatus
from app.models.wardrobe import WardrobeItem


@pytest.mark.asyncio
async def test_outfit_studio_crud_and_canvas_state(async_client: AsyncClient, db_session):
    headers = {"Authorization": "Bearer dev-token:stylist@aura-wardrobe.app"}
    sync_resp = await async_client.post("/api/v1/auth/sync", headers=headers)
    user_id = uuid.UUID(sync_resp.json()["id"])

    # 1. Insert 2 sample wardrobe items for the user
    item1 = WardrobeItem(
        user_id=user_id,
        name="Oversized Linen Shirt",
        category=ClothingCategory.TOP,
        original_image_url="/static/originals/shirt.jpg",
        cutout_image_url="/static/cutouts/shirt_cutout.png",
        status=ProcessingStatus.COMPLETED
    )
    item2 = WardrobeItem(
        user_id=user_id,
        name="Pleated Wool Trousers",
        category=ClothingCategory.BOTTOM,
        original_image_url="/static/originals/trousers.jpg",
        cutout_image_url="/static/cutouts/trousers_cutout.png",
        status=ProcessingStatus.COMPLETED
    )
    db_session.add_all([item1, item2])
    await db_session.commit()
    await db_session.refresh(item1)
    await db_session.refresh(item2)

    # 2. Test saving outfit with drag-and-drop canvas state
    canvas_payload = {
        "name": "Minimalist Autumn Gallery Look",
        "description": "Clean drape pairing oversized linen with structured wool.",
        "occasions": ["office_work", "casual_daily"],
        "season": "fall",
        "canvas_state": {
            "background_color": "#141418",
            "items": [
                {
                    "item_id": str(item1.id),
                    "x": 140.0,
                    "y": 60.0,
                    "scale": 1.1,
                    "rotation": -0.05,
                    "z_index": 1
                },
                {
                    "item_id": str(item2.id),
                    "x": 150.0,
                    "y": 240.0,
                    "scale": 1.0,
                    "rotation": 0.0,
                    "z_index": 2
                }
            ]
        },
        "preview_image_url": "/static/outfits/preview_1.png",
        "is_favorite": True
    }

    create_resp = await async_client.post("/api/v1/outfits", headers=headers, json=canvas_payload)
    assert create_resp.status_code == 201
    outfit_data = create_resp.json()
    outfit_id = outfit_data["id"]
    assert outfit_data["name"] == "Minimalist Autumn Gallery Look"
    assert outfit_data["season"] == "fall"
    assert outfit_data["items_count"] == 2
    assert len(outfit_data["items"]) == 2
    assert outfit_data["canvas_state"]["items"][0]["item_id"] == str(item1.id)
    assert outfit_data["canvas_state"]["items"][1]["z_index"] == 2

    # 3. Test listing outfits with occasion filter
    list_resp = await async_client.get("/api/v1/outfits?occasion=office_work", headers=headers)
    assert list_resp.status_code == 200
    outfits = list_resp.json()
    assert len(outfits) >= 1
    assert outfits[0]["id"] == outfit_id

    # 4. Test getting single outfit
    get_resp = await async_client.get(f"/api/v1/outfits/{outfit_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Minimalist Autumn Gallery Look"

    # 5. Test updating canvas coordinates (moving item on canvas)
    updated_canvas = outfit_data["canvas_state"]
    updated_canvas["items"][0]["x"] = 180.0
    updated_canvas["items"][0]["scale"] = 1.25

    patch_resp = await async_client.patch(
        f"/api/v1/outfits/{outfit_id}",
        headers=headers,
        json={
            "name": "Updated Gallery Uniform",
            "canvas_state": updated_canvas
        }
    )
    assert patch_resp.status_code == 200
    patched_data = patch_resp.json()
    assert patched_data["name"] == "Updated Gallery Uniform"
    assert patched_data["canvas_state"]["items"][0]["x"] == 180.0
    assert patched_data["canvas_state"]["items"][0]["scale"] == 1.25

    # 6. Test unauthorized item in canvas rejection
    fake_item_id = str(uuid.uuid4())
    invalid_canvas = {
        "name": "Invalid Outfit",
        "canvas_state": {
            "items": [{"item_id": fake_item_id, "x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "z_index": 0}]
        }
    }
    invalid_resp = await async_client.post("/api/v1/outfits", headers=headers, json=invalid_canvas)
    assert invalid_resp.status_code == 400
    assert "not found in your wardrobe" in invalid_resp.json()["detail"]

    # 7. Test delete outfit
    del_resp = await async_client.delete(f"/api/v1/outfits/{outfit_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # Verify 404
    get_after_del = await async_client.get(f"/api/v1/outfits/{outfit_id}", headers=headers)
    assert get_after_del.status_code == 404


# ---------- Milestone 3 hardening ----------

import io as _io
from PIL import Image as _Image
from app.services.storage import storage_service


async def _setup_user_with_items(async_client, db_session, email, n=2):
    headers = {"Authorization": f"Bearer dev-token:{email}"}
    user_id = uuid.UUID((await async_client.post("/api/v1/auth/sync", headers=headers)).json()["id"])
    items = [
        WardrobeItem(
            user_id=user_id, name=f"Garment {i}", category=ClothingCategory.TOP,
            original_image_url=f"/static/originals/{i}.jpg", cutout_image_url=f"/static/cutouts/{i}.png",
            status=ProcessingStatus.COMPLETED,
        )
        for i in range(n)
    ]
    db_session.add_all(items)
    await db_session.commit()
    return headers, items


def _canvas(*items, **extra):
    return {
        "items": [
            {"item_id": str(it.id), "x": 10.0 * i, "y": 20.0 * i, "scale": 1.0, "rotation": 0.3, "z_index": i}
            for i, it in enumerate(items)
        ],
        **extra,
    }


def _png_bytes(size=(64, 96)) -> bytes:
    buf = _io.BytesIO()
    _Image.new("RGBA", size, (20, 20, 24, 255)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_canvas_dimensions_round_trip(async_client: AsyncClient, db_session):
    headers, items = await _setup_user_with_items(async_client, db_session, "dims@aura.app")
    resp = await async_client.post("/api/v1/outfits", headers=headers, json={
        "name": "Dims", "canvas_state": _canvas(*items, canvas_width=390.0, canvas_height=640.0),
    })
    assert resp.status_code == 201
    state = resp.json()["canvas_state"]
    assert state["canvas_width"] == 390.0 and state["canvas_height"] == 640.0
    assert state["items"][1]["rotation"] == 0.3
    # Items are returned back-to-front
    assert [i["id"] for i in resp.json()["items"]] == [str(items[0].id), str(items[1].id)]


@pytest.mark.asyncio
async def test_duplicate_canvas_items_rejected(async_client: AsyncClient, db_session):
    headers, items = await _setup_user_with_items(async_client, db_session, "dupes@aura.app", n=1)
    resp = await async_client.post("/api/v1/outfits", headers=headers, json={
        "name": "Dupes", "canvas_state": _canvas(items[0], items[0]),
    })
    assert resp.status_code == 400
    assert "only be placed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_patch_rejects_garments_from_another_wardrobe(async_client: AsyncClient, db_session):
    headers, items = await _setup_user_with_items(async_client, db_session, "owner@aura.app")
    _, foreign_items = await _setup_user_with_items(async_client, db_session, "other@aura.app", n=1)

    outfit = (await async_client.post("/api/v1/outfits", headers=headers, json={
        "name": "Mine", "canvas_state": _canvas(*items),
    })).json()

    resp = await async_client.patch(f"/api/v1/outfits/{outfit['id']}", headers=headers, json={
        "canvas_state": _canvas(items[0], foreign_items[0]),
    })
    assert resp.status_code == 400
    assert "not found in your wardrobe" in resp.json()["detail"]

    # Unchanged after the rejected patch
    after = (await async_client.get(f"/api/v1/outfits/{outfit['id']}", headers=headers)).json()
    assert {i["id"] for i in after["items"]} == {str(i.id) for i in items}


@pytest.mark.asyncio
async def test_patch_canvas_resyncs_item_breakdown(async_client: AsyncClient, db_session):
    headers, items = await _setup_user_with_items(async_client, db_session, "resync@aura.app", n=3)
    outfit = (await async_client.post("/api/v1/outfits", headers=headers, json={
        "name": "Resync", "canvas_state": _canvas(items[0], items[1]),
    })).json()

    resp = await async_client.patch(f"/api/v1/outfits/{outfit['id']}", headers=headers, json={
        "canvas_state": _canvas(items[2], items[0]),
    })
    assert resp.status_code == 200
    assert [i["id"] for i in resp.json()["items"]] == [str(items[2].id), str(items[0].id)]
    assert resp.json()["items_count"] == 2


@pytest.mark.asyncio
async def test_preview_upload_replace_and_cleanup(async_client: AsyncClient, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(storage_service, "local_dir", tmp_path)
    headers, items = await _setup_user_with_items(async_client, db_session, "preview@aura.app")
    outfit = (await async_client.post("/api/v1/outfits", headers=headers, json={
        "name": "Preview", "canvas_state": _canvas(*items),
    })).json()
    url = f"/api/v1/outfits/{outfit['id']}/preview"

    first = await async_client.post(url, headers=headers, files={"file": ("p.png", _png_bytes(), "image/png")})
    assert first.status_code == 200
    first_url = first.json()["preview_image_url"]
    assert first_url.startswith("/static/outfits/") and first_url.endswith(".png")
    assert len(list((tmp_path / "outfits").iterdir())) == 1

    second = await async_client.post(url, headers=headers, files={"file": ("p.png", _png_bytes((80, 80)), "image/png")})
    second_url = second.json()["preview_image_url"]
    assert second_url != first_url
    assert [p.name for p in (tmp_path / "outfits").iterdir()] == [second_url.rsplit("/", 1)[1]]  # old one deleted

    jpeg = _io.BytesIO()
    _Image.new("RGB", (32, 32)).save(jpeg, format="JPEG")
    bad = await async_client.post(url, headers=headers, files={"file": ("p.jpg", jpeg.getvalue(), "image/jpeg")})
    assert bad.status_code == 400
    garbage = await async_client.post(url, headers=headers, files={"file": ("p.png", b"nope", "image/png")})
    assert garbage.status_code == 400

    other_headers = {"Authorization": "Bearer dev-token:intruder@aura.app"}
    await async_client.post("/api/v1/auth/sync", headers=other_headers)
    foreign = await async_client.post(url, headers=other_headers, files={"file": ("p.png", _png_bytes(), "image/png")})
    assert foreign.status_code == 404

    assert (await async_client.delete(f"/api/v1/outfits/{outfit['id']}", headers=headers)).status_code == 200
    assert list((tmp_path / "outfits").iterdir()) == []

"""
AI stylist engine: outfit validation, rule engine, Gemini engine (mocked), anchors, weather by city,
plus wear tracking, the GDPR asset purge and the dev schema sync.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select

from app.models.wardrobe import ClothingCategory, ProcessingStatus, WardrobeItem
from app.services.gemini import GeminiClient
from app.services.llm_stylist import LLMStylistService, validate_outfit

HEADERS = {"Authorization": "Bearer dev-token:engine@aura.app"}
WEATHER = {
    "temperature_c": 22.0, "apparent_temperature_c": 22.0, "humidity_pct": 50, "wind_speed_kmh": 5.0,
    "weather_code": 1, "condition": "Mainly clear", "is_rainy": False, "is_cold": False, "is_hot": False,
}
COLD_RAIN = {**WEATHER, "temperature_c": 9.0, "condition": "Slight rain", "is_rainy": True, "is_cold": True}
PREFS = {"style_vibes": ["minimalist"], "preferred_colors": [], "avoided_colors": [], "sizing_preference": "regular"}


def item(cat, name, color="black", **kw):
    return {"id": str(uuid.uuid4()), "name": name, "category": cat, "primary_color": color,
            "seasons": ["all_season"], "occasions": [], **kw}


@pytest.fixture
def closet():
    return {
        "tee": item("top", "White Tee", "white"),
        "shirt": item("top", "Blue Oxford", "light blue", occasions=["office_work"]),
        "jeans": item("bottom", "Dark Jeans", "navy"),
        "chinos": item("bottom", "Beige Chinos", "beige", occasions=["office_work"]),
        "dress": item("dress", "Black Slip Dress", "black"),
        "coat": item("outerwear", "Trench Coat", "beige"),
        "boots": item("footwear", "Chelsea Boots", "brown"),
        "watch": item("accessory", "Watch", "grey"),
        "belt": item("accessory", "Belt", "brown"),
        "ring": item("accessory", "Ring", "grey"),
    }


def ids(closet, *names):
    return [closet[n]["id"] for n in names]


# ---------------- validate_outfit ----------------

def test_validate_drops_unknown_duplicates_and_enforces_slot_limits(closet):
    by_id = {i["id"]: i for i in closet.values()}
    raw = ids(closet, "tee", "shirt", "jeans", "chinos", "watch", "belt", "ring") + ["made-up", closet["tee"]["id"]]
    kept, missing = validate_outfit(raw, by_id)
    assert kept == ids(closet, "tee", "jeans", "watch", "belt")  # 1 top, 1 bottom, 2 accessories
    assert missing == []


def test_validate_dress_displaces_separates_unless_a_separate_is_anchored(closet):
    by_id = {i["id"]: i for i in closet.values()}
    kept, missing = validate_outfit(ids(closet, "tee", "jeans", "dress", "boots"), by_id)
    assert kept == ids(closet, "dress", "boots") and missing == []

    kept, missing = validate_outfit(ids(closet, "dress", "jeans", "boots"), by_id, anchor_ids=ids(closet, "tee"))
    assert kept == ids(closet, "tee", "jeans", "boots") and missing == []


def test_validate_reports_missing_core_pieces(closet):
    by_id = {i["id"]: i for i in closet.values()}
    kept, missing = validate_outfit(ids(closet, "tee", "boots"), by_id)
    assert kept == ids(closet, "tee", "boots") and missing == ["bottom"]


# ---------------- rule engine ----------------

@pytest.mark.asyncio
async def test_rule_engine_builds_distinct_complete_looks_and_layers_in_rain(closet):
    svc = LLMStylistService(provider="rules")
    outfits, engine = await svc.suggest_outfits(list(closet.values()), COLD_RAIN, "office_work", PREFS, num_outfits=3)
    assert engine == "rule_engine" and len(outfits) == 3
    assert len({frozenset(o["item_ids"]) for o in outfits}) == 3
    by_id = {i["id"]: i for i in closet.values()}
    for o in outfits:
        assert o["is_complete"]
        cats = [by_id[i]["category"] for i in o["item_ids"]]
        assert "outerwear" in cats  # cold + rain
        assert "rain" in o["rationale"].lower()
    # Office items score highest, so the first look is the office pairing
    assert set(ids(closet, "shirt", "chinos")) <= set(outfits[0]["item_ids"])


@pytest.mark.asyncio
async def test_rule_engine_avoids_recently_worn_and_avoided_colours(closet):
    closet["tee"]["last_worn_at"] = datetime.now(timezone.utc) - timedelta(hours=5)
    prefs = {**PREFS, "avoided_colors": ["navy"]}
    svc = LLMStylistService(provider="rules")
    outfits, _ = await svc.suggest_outfits(
        [closet[n] for n in ("tee", "shirt", "jeans", "chinos")], WEATHER, "casual_daily", prefs, num_outfits=1
    )
    assert outfits[0]["item_ids"] == ids(closet, "shirt", "chinos")


@pytest.mark.asyncio
async def test_rule_engine_handles_tops_only_wardrobe():
    shirts = [item("top", "Pink Polo", "pink"), item("top", "Floral Shirt", "cream")]
    svc = LLMStylistService(provider="rules")
    outfits, _ = await svc.suggest_outfits(shirts, WEATHER, "casual_daily", PREFS, num_outfits=3)
    assert len(outfits) == 2
    for o in outfits:
        assert not o["is_complete"] and o["missing_categories"] == ["bottom"]
        assert o["missing_pieces"]


@pytest.mark.asyncio
async def test_rule_engine_includes_anchor_in_every_look(closet):
    svc = LLMStylistService(provider="rules")
    anchor = closet["jeans"]["id"]
    outfits, _ = await svc.suggest_outfits(
        list(closet.values()), WEATHER, "casual_daily", PREFS, num_outfits=2, anchor_ids=[anchor]
    )
    assert len(outfits) == 2
    assert all(anchor in o["item_ids"] for o in outfits)
    assert all(closet["dress"]["id"] not in o["item_ids"] for o in outfits)


# ---------------- Gemini engine ----------------

def gemini_returning(payload, captured):
    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]})
    return GeminiClient(api_key="k", transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_gemini_engine_maps_refs_validates_and_tops_up(closet):
    items = list(closet.values())  # refs: i1=tee i2=shirt i3=jeans i4=chinos i5=dress ...
    payload = {"outfits": [
        {"name": "Weekend Ease", "item_refs": ["i1", "i3", "i7", "i99"], "rationale": "Easy and clean.",
         "styling_tips": ["Cuff the jeans.", " "], "missing_pieces": []},
        {"name": "Mixed Up", "item_refs": ["i5", "i1", "i3"], "rationale": "Dress wins."},
        {"name": "Duplicate", "item_refs": ["i3", "i1", "i7"], "rationale": "Same as the first."},
    ]}
    captured = []
    svc = LLMStylistService(provider="gemini", gemini=gemini_returning(payload, captured))
    outfits, engine = await svc.suggest_outfits(
        items, WEATHER, "casual_daily", PREFS, num_outfits=3, user_request="coffee date"
    )
    assert engine == "gemini" and len(outfits) == 3
    assert outfits[0]["item_ids"] == ids(closet, "tee", "jeans", "boots")
    assert outfits[0]["styling_tips"] == ["Cuff the jeans."]
    assert outfits[1]["item_ids"] == ids(closet, "dress")
    assert outfits[2]["name"] not in {"Weekend Ease", "Mixed Up", "Duplicate"}  # topped up by the rule engine

    prompt = captured[0]["contents"][0]["parts"][0]["text"]
    assert "coffee date" in prompt and "i1 | White Tee | top" in prompt
    assert closet["tee"]["id"] not in prompt  # UUIDs never reach the model
    assert captured[0]["generationConfig"]["responseSchema"]["required"] == ["outfits"]


@pytest.mark.asyncio
async def test_gemini_failure_falls_back_to_rules(closet):
    failing = GeminiClient(api_key="k", transport=httpx.MockTransport(lambda r: httpx.Response(503, text="down")))
    svc = LLMStylistService(provider="gemini", gemini=failing)
    outfits, engine = await svc.suggest_outfits(list(closet.values()), WEATHER, "casual_daily", PREFS, 2)
    assert engine == "rule_engine" and len(outfits) == 2


# ---------------- endpoints ----------------

async def seed(async_client, db_session, specs):
    from app.models.user import User

    await async_client.post("/api/v1/auth/sync", headers=HEADERS)
    user = (await db_session.execute(select(User).where(User.email == "engine@aura.app"))).scalar_one()
    rows = []
    for cat, name, color in specs:
        row = WardrobeItem(
            user_id=user.id, name=name, category=cat, primary_color=color,
            original_image_url="/static/originals/x.jpg", cutout_image_url="/static/cutouts/x.png",
            status=ProcessingStatus.COMPLETED,
        )
        db_session.add(row)
        rows.append(row)
    await db_session.commit()
    return rows


@pytest.mark.asyncio
async def test_suggest_endpoint_returns_items_weather_and_honours_anchor(async_client, db_session):
    rows = await seed(async_client, db_session, [
        (ClothingCategory.TOP, "Tee", "white"), (ClothingCategory.TOP, "Polo", "pink"),
        (ClothingCategory.BOTTOM, "Jeans", "navy"), (ClothingCategory.FOOTWEAR, "Sneakers", "white"),
    ])
    polo = str(rows[1].id)
    geo = {"latitude": 19.07, "longitude": 72.87, "name": "Mumbai, India"}
    with patch("app.api.v1.endpoints.stylist.weather_service.geocode", new_callable=AsyncMock, return_value=geo), \
         patch("app.api.v1.endpoints.stylist.weather_service.get_current_weather", new_callable=AsyncMock,
               return_value={**WEATHER, "temperature_c": 31.0, "is_hot": True}) as weather_mock:
        resp = await async_client.post("/api/v1/stylist/suggest", headers=HEADERS, json={
            "occasion": "casual_daily", "city": "Mumbai", "anchor_item_ids": [polo],
            "prompt": "lunch with friends", "num_outfits": 2,
        })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    weather_mock.assert_awaited_once_with(latitude=19.07, longitude=72.87)
    assert data["weather"]["location_name"] == "Mumbai, India"
    assert data["weather"]["temperature_c"] == 31.0 and not data["weather"]["is_fallback"]
    assert data["engine"] == "rule_engine"
    look = data["outfits"][0]
    assert polo in look["item_ids"] and look["is_complete"]
    assert [i["id"] for i in look["items"]] == look["item_ids"]
    assert look["items"][0]["cutout_image_url"]


@pytest.mark.asyncio
async def test_suggest_rejects_foreign_anchor_and_weather_endpoint(async_client, db_session):
    await seed(async_client, db_session, [(ClothingCategory.TOP, "Tee", "white")])
    resp = await async_client.post("/api/v1/stylist/suggest", headers=HEADERS,
                                   json={"anchor_item_ids": [str(uuid.uuid4())]})
    assert resp.status_code == 404

    with patch("app.api.v1.endpoints.stylist.weather_service.geocode", new_callable=AsyncMock, return_value=None):
        resp = await async_client.get("/api/v1/stylist/weather", headers=HEADERS, params={"city": "Atlantis"})
    assert resp.status_code == 404

    resp = await async_client.get("/api/v1/stylist/weather", headers=HEADERS)
    assert resp.status_code == 200 and resp.json()["is_fallback"]


# ---------------- wear tracking ----------------

@pytest.mark.asyncio
async def test_wear_endpoint_increments_counts(async_client, db_session):
    rows = await seed(async_client, db_session, [
        (ClothingCategory.TOP, "Tee", "white"), (ClothingCategory.BOTTOM, "Jeans", "navy"),
    ])
    body = {"item_ids": [str(rows[0].id), str(rows[1].id), str(rows[0].id)]}
    resp = await async_client.post("/api/v1/wardrobe/items/wear", headers=HEADERS, json=body)
    assert resp.status_code == 200
    assert sorted(i["wear_count"] for i in resp.json()) == [1, 1]  # duplicate id counted once
    assert all(i["last_worn_at"] for i in resp.json())

    resp = await async_client.post("/api/v1/wardrobe/items/wear", headers=HEADERS,
                                   json={"item_ids": [str(uuid.uuid4())]})
    assert resp.status_code == 404


# ---------------- GDPR purge deletes stored files ----------------

@pytest.mark.asyncio
async def test_delete_my_data_removes_stored_assets(async_client, db_session):
    from app.services.storage import storage_service

    await async_client.post("/api/v1/auth/sync", headers=HEADERS)
    url = await storage_service.save_file(b"pixels", f"gdpr_{uuid.uuid4().hex}.png", subfolder="showcase")
    rows = await seed(async_client, db_session, [(ClothingCategory.TOP, "Tee", "white")])
    rows[0].showcase_image_url = url
    await db_session.commit()
    path = storage_service._local_path(url)
    assert Path(path).exists()
    outfit = await async_client.post("/api/v1/outfits", headers=HEADERS, json={
        "name": "Look", "canvas_state": {"items": [{"item_id": str(rows[0].id)}]},
    })
    assert outfit.status_code == 201

    resp = await async_client.delete("/api/v1/users/me/delete-data", headers=HEADERS)
    assert resp.status_code == 200
    assert not Path(path).exists()
    from app.models.outfit import Outfit, OutfitItem
    assert (await db_session.execute(select(Outfit))).first() is None
    assert (await db_session.execute(select(OutfitItem))).first() is None
    assert (await db_session.execute(select(WardrobeItem))).first() is None


# ---------------- dev schema sync ----------------

def test_dev_schema_sync_adds_missing_columns(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from app.db.base import Base
    from app.db.dev_schema import add_missing_columns
    import app.models  # noqa: F401  (register tables)

    engine = create_engine(f"sqlite:///{tmp_path / 'dev.db'}")
    with engine.begin() as conn:
        Base.metadata.create_all(conn)
        conn.execute(text("ALTER TABLE wardrobe_items DROP COLUMN showcase_image_url"))
        conn.execute(text("ALTER TABLE wardrobe_items DROP COLUMN category_user_set"))
        added = add_missing_columns(conn)
    assert set(added) == {"wardrobe_items.showcase_image_url", "wardrobe_items.category_user_set"}
    cols = {c["name"] for c in inspect(engine).get_columns("wardrobe_items")}
    assert {"showcase_image_url", "category_user_set"} <= cols


# ---------------- garment knowledge, variety and weather (found in the live benchmark) ----------------

def test_rule_engine_varies_pieces_across_looks_in_one_response():
    closet = [item("top", f"Tee {n}", c, sub_category="t-shirt") for n, c in enumerate(["white", "black", "grey"])]
    closet += [item("bottom", f"Jeans {n}", c, sub_category="jeans") for n, c in enumerate(["navy", "black", "grey"])]
    closet += [item("footwear", f"Sneakers {n}", "white", sub_category="sneakers") for n in range(3)]
    svc = LLMStylistService(provider="rules", seed=1)
    outfits, _ = await_rules(svc, closet, WEATHER, "casual_daily", 3)
    tops = [i for o in outfits for i in o["item_ids"] if i in {c["id"] for c in closet[:3]}]
    shoes = [i for o in outfits for i in o["item_ids"] if i in {c["id"] for c in closet[6:]}]
    assert len(set(tops)) == 3 and len(set(shoes)) == 3


def test_rule_engine_dresses_for_heat_cold_and_formality():
    closet = [
        item("top", "Linen Tee", "white", sub_category="t-shirt"),
        item("top", "Oxford", "light blue", sub_category="button-up shirt"),
        item("bottom", "Shorts", "beige", sub_category="shorts"),
        item("bottom", "Chinos", "navy", sub_category="chinos"),
        item("outerwear", "Hoodie", "grey", sub_category="hoodie"),
        item("outerwear", "Blazer", "navy", sub_category="blazer"),
        item("footwear", "Sneakers", "white", sub_category="sneakers"),
        item("footwear", "Loafers", "brown", sub_category="loafers"),
    ]
    names = lambda o: {i["name"] for i in closet if i["id"] in o["item_ids"]}
    svc = LLMStylistService(provider="rules", seed=3)

    hot = {**WEATHER, "temperature_c": 31.0, "is_hot": True, "is_rainy": True, "condition": "Light drizzle"}
    look = await_rules(svc, closet, hot, "casual_daily", 1)[0][0]
    assert "Hoodie" not in names(look) and "Blazer" not in names(look)  # no heavy layer in 31°C drizzle

    cold = {**WEATHER, "temperature_c": 4.0, "is_cold": True}
    look = await_rules(svc, closet, cold, "casual_daily", 1)[0][0]
    assert "Shorts" not in names(look) and names(look) & {"Hoodie", "Blazer"}

    look = await_rules(svc, closet, WEATHER, "office_work", 1)[0][0]
    assert {"Oxford", "Chinos", "Loafers"} <= names(look)

    look = await_rules(svc, closet, WEATHER, "athleisure", 1)[0][0]
    assert {"Sneakers"} <= names(look) and "Loafers" not in names(look)


def await_rules(svc, closet, weather, occasion, n):
    import asyncio
    return asyncio.run(svc.suggest_outfits(closet, weather, occasion, PREFS, num_outfits=n))


@pytest.mark.asyncio
async def test_lookbook_returns_complete_unique_looks_per_occasion(async_client, db_session):
    await seed(async_client, db_session, [
        (ClothingCategory.TOP, "Tee", "white"), (ClothingCategory.TOP, "Oxford Shirt", "light blue"),
        (ClothingCategory.BOTTOM, "Jeans", "navy"), (ClothingCategory.BOTTOM, "Chinos", "beige"),
        (ClothingCategory.FOOTWEAR, "Sneakers", "white"),
    ])
    resp = await async_client.get("/api/v1/stylist/lookbook", headers=HEADERS, params={"per_occasion": 2})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sections"] and data["total_wardrobe_items"] == 5
    seen = set()
    for section in data["sections"]:
        assert 1 <= len(section["outfits"]) <= 2
        for look in section["outfits"]:
            assert look["is_complete"] and look["items"]
            key = frozenset(look["item_ids"])
            assert key not in seen  # no look repeated across occasions
            seen.add(key)
    # 2 tops x 2 bottoms = 4 possible base looks in total
    assert len(seen) <= 4


@pytest.mark.asyncio
async def test_lookbook_skips_occasions_without_a_complete_look(async_client, db_session):
    await seed(async_client, db_session, [(ClothingCategory.TOP, "Tee", "white")])
    resp = await async_client.get("/api/v1/stylist/lookbook", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["sections"] == []

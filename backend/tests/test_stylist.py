"""
Tests for Milestone 4: AI Stylist endpoints and services.

Validates:
  - POST /api/v1/stylist/suggest with completed wardrobe items (rule engine fallback)
  - 422 when no completed items exist
  - Weather service fallback behavior
  - Rule-based suggestion engine generates valid outfit structures
  - Auth required for stylist endpoint
"""

import pytest
import uuid
from unittest.mock import patch, AsyncMock

AUTH_HEADERS = {"Authorization": "Bearer dev-token:stylist@aura.app"}


@pytest.mark.asyncio
async def test_stylist_suggest_requires_completed_items(async_client):
    """Stylist rejects requests when user has no completed wardrobe items."""
    # Create user via auth sync
    await async_client.post(
        "/api/v1/auth/sync",
        headers=AUTH_HEADERS,
        json={"display_name": "Stylist Tester"},
    )

    response = await async_client.post(
        "/api/v1/stylist/suggest",
        headers=AUTH_HEADERS,
        json={"occasion": "casual_daily"},
    )
    assert response.status_code == 422
    assert "No completed wardrobe items" in response.json()["detail"]


@pytest.mark.asyncio
async def test_stylist_suggest_with_wardrobe_items(async_client, db_session):
    """Stylist generates outfit suggestions from completed wardrobe items."""
    # Create user
    await async_client.post(
        "/api/v1/auth/sync",
        headers=AUTH_HEADERS,
        json={"display_name": "Stylist User"},
    )

    # Get user from DB for direct item insertion
    from app.models.user import User
    from app.models.wardrobe import WardrobeItem, ProcessingStatus, ClothingCategory
    from sqlalchemy import select

    result = await db_session.execute(select(User))
    user = result.scalars().first()

    # Create multiple completed wardrobe items spanning categories
    items_data = [
        {"category": ClothingCategory.TOP, "name": "White Linen Shirt", "primary_color": "white", "sub_category": "linen shirt"},
        {"category": ClothingCategory.TOP, "name": "Black Tee", "primary_color": "black", "sub_category": "crew neck tee"},
        {"category": ClothingCategory.BOTTOM, "name": "Navy Chinos", "primary_color": "navy blue", "sub_category": "chinos"},
        {"category": ClothingCategory.BOTTOM, "name": "Dark Jeans", "primary_color": "black", "sub_category": "slim jeans"},
        {"category": ClothingCategory.OUTERWEAR, "name": "Olive Bomber", "primary_color": "olive green", "sub_category": "bomber jacket"},
        {"category": ClothingCategory.FOOTWEAR, "name": "White Sneakers", "primary_color": "white", "sub_category": "sneakers"},
        {"category": ClothingCategory.ACCESSORY, "name": "Silver Watch", "primary_color": "grey", "sub_category": "watch"},
    ]

    for item_data in items_data:
        item = WardrobeItem(
            user_id=user.id,
            name=item_data["name"],
            category=item_data["category"],
            sub_category=item_data["sub_category"],
            primary_color=item_data["primary_color"],
            original_image_url="/test/placeholder.jpg",
            cutout_image_url="/test/cutout.png",
            status=ProcessingStatus.COMPLETED,
            clip_embedding=[0.0] * 512,
        )
        db_session.add(item)

    await db_session.commit()

    # Request outfit suggestions (no lat/lon = fallback weather)
    response = await async_client.post(
        "/api/v1/stylist/suggest",
        headers=AUTH_HEADERS,
        json={
            "occasion": "casual_daily",
            "num_outfits": 3,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert "outfits" in data
    assert len(data["outfits"]) >= 1
    assert len(data["outfits"]) <= 3
    assert data["occasion"] == "casual_daily"
    assert data["engine"] == "rule_engine"
    assert data["total_wardrobe_items"] == 7

    # Validate outfit structure
    for outfit in data["outfits"]:
        assert "name" in outfit
        assert "item_ids" in outfit
        assert len(outfit["item_ids"]) >= 1
        assert "rationale" in outfit
        assert len(outfit["rationale"]) > 10


@pytest.mark.asyncio
async def test_stylist_suggest_with_weather_coordinates(async_client, db_session):
    """Stylist fetches weather when lat/lon are provided."""
    # Create user
    await async_client.post(
        "/api/v1/auth/sync",
        headers=AUTH_HEADERS,
        json={"display_name": "Weather Tester"},
    )

    from app.models.user import User
    from app.models.wardrobe import WardrobeItem, ProcessingStatus, ClothingCategory
    from sqlalchemy import select

    result = await db_session.execute(select(User))
    user = result.scalars().first()

    # Add minimum items
    for cat, name in [(ClothingCategory.TOP, "Tee"), (ClothingCategory.BOTTOM, "Jeans")]:
        item = WardrobeItem(
            user_id=user.id,
            name=name,
            category=cat,
            primary_color="black",
            original_image_url="/test/img.jpg",
            cutout_image_url="/test/cut.png",
            status=ProcessingStatus.COMPLETED,
            clip_embedding=[0.0] * 512,
        )
        db_session.add(item)
    await db_session.commit()

    # Mock weather service to avoid external API call in tests
    mock_weather = {
        "temperature_c": 8.0,
        "apparent_temperature_c": 5.0,
        "humidity_pct": 80,
        "wind_speed_kmh": 25.0,
        "weather_code": 61,
        "condition": "Slight rain",
        "is_rainy": True,
        "is_cold": True,
        "is_hot": False,
    }

    with patch(
        "app.api.v1.endpoints.stylist.weather_service.get_current_weather",
        new_callable=AsyncMock,
        return_value=mock_weather,
    ):
        response = await async_client.post(
            "/api/v1/stylist/suggest",
            headers=AUTH_HEADERS,
            json={
                "occasion": "office_work",
                "latitude": 51.5074,
                "longitude": -0.1278,
                "num_outfits": 2,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "rain" in data["weather_summary"].lower() or "Slight rain" in data["weather_summary"]


@pytest.mark.asyncio
async def test_stylist_suggest_unauthenticated(async_client):
    """Stylist endpoint requires authentication."""
    response = await async_client.post(
        "/api/v1/stylist/suggest",
        json={"occasion": "casual_daily"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rule_engine_direct():
    """Directly test the rule-based engine with synthetic wardrobe data."""
    from app.services.llm_stylist import LLMStylistService

    service = LLMStylistService(provider="rules")

    wardrobe = [
        {"id": str(uuid.uuid4()), "name": "White Shirt", "category": "top", "sub_category": "oxford shirt", "primary_color": "white", "seasons": ["all_season"], "occasions": ["office_work"]},
        {"id": str(uuid.uuid4()), "name": "Grey Trousers", "category": "bottom", "sub_category": "trousers", "primary_color": "grey", "seasons": ["all_season"], "occasions": ["office_work"]},
        {"id": str(uuid.uuid4()), "name": "Navy Blazer", "category": "outerwear", "sub_category": "blazer", "primary_color": "navy blue", "seasons": ["fall", "winter"], "occasions": ["office_work"]},
        {"id": str(uuid.uuid4()), "name": "Black Oxfords", "category": "footwear", "sub_category": "oxford shoes", "primary_color": "black", "seasons": ["all_season"], "occasions": []},
    ]

    weather = {
        "temperature_c": 10.0,
        "apparent_temperature_c": 7.0,
        "humidity_pct": 65,
        "wind_speed_kmh": 20.0,
        "weather_code": 3,
        "condition": "Overcast",
        "is_rainy": False,
        "is_cold": True,
        "is_hot": False,
    }

    preferences = {
        "style_vibes": ["minimalist"],
        "preferred_colors": ["monochrome", "neutrals"],
        "avoided_colors": ["neon_yellow"],
        "sizing_preference": "regular",
    }

    outfits, engine = await service.suggest_outfits(
        wardrobe_items=wardrobe,
        weather=weather,
        occasion="office_work",
        preferences=preferences,
        num_outfits=2,
    )

    assert engine == "rule_engine"
    assert len(outfits) >= 1
    for outfit in outfits:
        assert "name" in outfit
        assert "item_ids" in outfit
        assert len(outfit["item_ids"]) >= 2  # At least top + bottom
        assert "rationale" in outfit
        # Validate all IDs come from the wardrobe
        valid_ids = {item["id"] for item in wardrobe}
        for iid in outfit["item_ids"]:
            assert iid in valid_ids


@pytest.mark.asyncio
async def test_weather_service_fallback():
    """Weather service returns fallback data when API call fails."""
    from app.services.weather import WeatherService

    service = WeatherService(timeout=0.001)  # Timeout immediately

    weather = await service.get_current_weather(latitude=0.0, longitude=0.0)
    assert weather["temperature_c"] == 20.0
    assert "fallback" in weather["condition"].lower()


@pytest.mark.asyncio
async def test_weather_prompt_snippet():
    """WeatherService generates a well-formatted prompt snippet."""
    from app.services.weather import WeatherService

    weather = {
        "temperature_c": 28.0,
        "apparent_temperature_c": 31.0,
        "humidity_pct": 75,
        "wind_speed_kmh": 5.0,
        "weather_code": 2,
        "condition": "Partly cloudy",
        "is_rainy": False,
        "is_cold": False,
        "is_hot": False,
    }

    snippet = WeatherService.weather_to_prompt_snippet(weather)
    assert "28.0°C" in snippet
    assert "Partly cloudy" in snippet
    assert "75%" in snippet

"""
AI Stylist API endpoints (Milestone 4).

POST /api/v1/stylist/suggest
    Generates outfit suggestions from the user's completed wardrobe items,
    conditioned on current weather (via Open-Meteo), an occasion tag, an optional
    free-text request and optional anchor garments that must be included.

GET /api/v1/stylist/lookbook
    Ready-made outfits for every occasion at once (the Outfits tab). Uses the fast
    local rule engine, so opening the tab never costs an LLM call.

GET /api/v1/stylist/weather
    Current weather for a city or coordinates (the stylist screen's weather chip).
"""

import logging
from typing import List, Dict, Any, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core import rate_limit
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User, UserPreference
from app.models.wardrobe import WardrobeItem, ProcessingStatus
from app.schemas.stylist import (
    LookbookResponse,
    LookbookSection,
    StylistRequest,
    StylistResponse,
    SuggestedOutfit,
    WeatherInfo,
)
from app.schemas.wardrobe import WardrobeItemResponse
from app.services.weather import weather_service, WeatherService
from app.services.llm_stylist import LLMStylistService, llm_stylist_service

logger = logging.getLogger(__name__)
router = APIRouter()

LOOKBOOK_OCCASIONS = ["casual_daily", "office_work", "evening_dinner", "nightlife", "athleisure", "formal_events"]
lookbook_engine = LLMStylistService(provider="rules")

NO_ITEMS_DETAIL = (
    "No completed wardrobe items found. Upload and process garments before requesting styling suggestions."
)


async def resolve_weather(
    city: Optional[str], latitude: Optional[float], longitude: Optional[float]
) -> Tuple[Dict[str, Any], WeatherInfo]:
    location_name = None
    if latitude is None or longitude is None:
        place = await weather_service.geocode(city) if city else None
        if place:
            latitude, longitude, location_name = place["latitude"], place["longitude"], place["name"]

    if latitude is not None and longitude is not None:
        weather = await weather_service.get_current_weather(latitude=latitude, longitude=longitude)
    else:
        weather = WeatherService._fallback_weather()

    info = WeatherInfo(
        location_name=location_name,
        temperature_c=weather["temperature_c"],
        apparent_temperature_c=weather["apparent_temperature_c"],
        condition=weather["condition"],
        is_rainy=weather["is_rainy"],
        is_cold=weather["is_cold"],
        is_hot=weather["is_hot"],
        is_fallback="fallback" in weather["condition"].lower(),
    )
    return weather, info


async def load_wardrobe(db: AsyncSession, user: User) -> Tuple[Dict[str, WardrobeItem], List[Dict[str, Any]]]:
    """Completed garments as ORM rows by id, plus the plain dicts the stylist engines take."""
    rows = (await db.execute(
        select(WardrobeItem)
        .where(WardrobeItem.user_id == user.id, WardrobeItem.status == ProcessingStatus.COMPLETED)
        .order_by(WardrobeItem.created_at)
    )).scalars().all()
    items = [
        {
            "id": str(item.id),
            "name": item.name,
            "category": item.category.value if hasattr(item.category, "value") else str(item.category),
            "sub_category": item.sub_category,
            "primary_color": item.primary_color,
            "secondary_color": item.secondary_color,
            "seasons": item.seasons or ["all_season"],
            "occasions": item.occasions or [],
            "brand": item.brand,
            "is_favorite": item.is_favorite,
            "wear_count": item.wear_count,
            "last_worn_at": item.last_worn_at,
        }
        for item in rows
    ]
    return {str(item.id): item for item in rows}, items


async def load_preferences(db: AsyncSession, user: User) -> Dict[str, Any]:
    pref = (await db.execute(
        select(UserPreference).where(UserPreference.user_id == user.id)
    )).scalar_one_or_none()
    return {
        "style_vibes": pref.style_vibes if pref else [],
        "preferred_colors": pref.preferred_colors if pref else [],
        "avoided_colors": pref.avoided_colors if pref else [],
        "sizing_preference": pref.sizing_preference if pref else "regular",
    }


def to_suggested(outfit: Dict[str, Any], rows_by_id: Dict[str, WardrobeItem]) -> SuggestedOutfit:
    return SuggestedOutfit(
        name=outfit["name"],
        item_ids=outfit["item_ids"],
        items=[WardrobeItemResponse.model_validate(rows_by_id[i]) for i in outfit["item_ids"]],
        occasion=outfit["occasion"],
        rationale=outfit["rationale"],
        styling_tips=outfit.get("styling_tips", []),
        is_complete=outfit.get("is_complete", True),
        missing_categories=outfit.get("missing_categories", []),
        missing_pieces=outfit.get("missing_pieces", []),
    )


@router.get("/weather", response_model=WeatherInfo, summary="Current weather for the stylist")
async def get_weather(
    city: Optional[str] = Query(None, max_length=100),
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    current_user: User = Depends(get_current_user),
):
    if city and latitude is None and not await weather_service.geocode(city):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Could not find a city called '{city}'.")
    _, info = await resolve_weather(city, latitude, longitude)
    return info


@router.get("/lookbook", response_model=LookbookResponse, summary="Ready-made outfits for every occasion")
async def get_lookbook(
    city: Optional[str] = Query(None, max_length=100),
    per_occasion: int = Query(2, ge=1, le=4),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Builds a few complete looks per occasion from the user's wardrobe and today's weather.
    Occasions the wardrobe cannot dress (no complete look) are left out, and a look already
    shown under an earlier occasion is not repeated.
    """
    rows_by_id, items = await load_wardrobe(db, current_user)
    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=NO_ITEMS_DETAIL)
    weather, weather_info = await resolve_weather(city, None, None)
    preferences = await load_preferences(db, current_user)

    seen = set()
    sections: List[LookbookSection] = []
    for occasion in LOOKBOOK_OCCASIONS:
        # Ask for spares so duplicates of earlier sections can be dropped
        outfits, _ = await lookbook_engine.suggest_outfits(
            items, weather, occasion, preferences, num_outfits=per_occasion + 2
        )
        fresh = []
        for o in outfits:
            key = frozenset(o["item_ids"])
            if o["is_complete"] and key not in seen:
                seen.add(key)
                fresh.append(to_suggested(o, rows_by_id))
            if len(fresh) == per_occasion:
                break
        if fresh:
            sections.append(LookbookSection(occasion=occasion, outfits=fresh))

    return LookbookResponse(sections=sections, weather=weather_info, total_wardrobe_items=len(items))


@router.post(
    "/suggest",
    response_model=StylistResponse,
    summary="AI Stylist: Generate outfit suggestions",
    description=(
        "Fetches the user's completed wardrobe items and style preferences, "
        "queries current weather for their city or coordinates, "
        "and generates outfit suggestions via Gemini (or the rule-based fallback engine)."
    ),
)
async def suggest_outfits(
    request: StylistRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await rate_limit.stylist_requests.enforce(str(current_user.id), "You've asked the stylist a lot this hour. Try again soon.")
    rows_by_id, wardrobe_items = await load_wardrobe(db, current_user)
    if not wardrobe_items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=NO_ITEMS_DETAIL)

    anchor_ids = [str(a) for a in request.anchor_item_ids]
    if any(a not in rows_by_id for a in anchor_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Some of the garments to style are not in your wardrobe (or are still processing).",
        )

    weather, weather_info = await resolve_weather(request.city, request.latitude, request.longitude)
    preferences = await load_preferences(db, current_user)

    try:
        raw_outfits, engine = await llm_stylist_service.suggest_outfits(
            wardrobe_items=wardrobe_items,
            weather=weather,
            occasion=request.occasion,
            preferences=preferences,
            num_outfits=request.num_outfits,
            user_request=request.prompt,
            anchor_ids=anchor_ids,
        )
    except Exception as e:
        logger.exception(f"Stylist suggestion engine error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stylist engine encountered an error. Please try again.",
        )

    return StylistResponse(
        outfits=[to_suggested(o, rows_by_id) for o in raw_outfits],
        weather=weather_info,
        weather_summary=WeatherService.weather_to_prompt_snippet(weather),
        occasion=request.occasion,
        total_wardrobe_items=len(wardrobe_items),
        engine=engine,
    )

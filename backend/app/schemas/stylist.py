"""
Pydantic schemas for the AI Stylist feature (Milestone 4).
"""

import uuid
from typing import Optional, List
from pydantic import BaseModel, Field

from app.schemas.wardrobe import WardrobeItemResponse


class StylistRequest(BaseModel):
    """Request body for AI styling consultation."""
    occasion: str = Field(
        default="casual_daily",
        description="Target occasion: office_work, casual_daily, evening_dinner, nightlife, formal_events, athleisure",
        examples=["casual_daily"],
    )
    prompt: Optional[str] = Field(
        default=None,
        max_length=300,
        description="Free-text request, e.g. 'brunch with friends, relaxed but put together'",
    )
    city: Optional[str] = Field(
        default=None,
        max_length=100,
        description="City for the weather lookup (used when latitude/longitude are omitted)",
        examples=["Mumbai"],
    )
    latitude: Optional[float] = Field(
        default=None,
        description="User latitude for weather lookup (Open-Meteo). Neutral 20°C weather is assumed if no location is given.",
        examples=[40.7128],
    )
    longitude: Optional[float] = Field(
        default=None,
        description="User longitude for weather lookup.",
        examples=[-74.0060],
    )
    anchor_item_ids: List[uuid.UUID] = Field(
        default_factory=list,
        max_length=6,
        description="Garments that must appear in every suggestion ('style this piece', 'complete this look')",
    )
    num_outfits: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Number of outfit suggestions to generate (1–5).",
    )


class WeatherInfo(BaseModel):
    location_name: Optional[str] = None
    temperature_c: float
    apparent_temperature_c: float
    condition: str
    is_rainy: bool = False
    is_cold: bool = False
    is_hot: bool = False
    is_fallback: bool = Field(default=False, description="True when no location was given or the lookup failed")


class SuggestedOutfit(BaseModel):
    """A single AI-generated outfit suggestion."""
    name: str = Field(..., description="Descriptive title for the outfit")
    item_ids: List[str] = Field(..., description="Wardrobe item UUIDs composing this outfit")
    items: List[WardrobeItemResponse] = Field(default_factory=list, description="The garments, in item_ids order")
    occasion: str = Field(..., description="Occasion tag")
    rationale: str = Field(..., description="2-3 sentence styling rationale explaining why these pieces work together")
    styling_tips: List[str] = Field(default_factory=list)
    is_complete: bool = Field(default=True, description="False when the wardrobe lacks a core piece for this look")
    missing_categories: List[str] = Field(default_factory=list, description="Core categories the look still needs")
    missing_pieces: List[str] = Field(default_factory=list, description="Suggested pieces to add to the wardrobe")


class StylistResponse(BaseModel):
    """Response payload containing outfit suggestions and context."""
    outfits: List[SuggestedOutfit]
    weather: WeatherInfo
    weather_summary: str = Field(
        ...,
        description="Human-readable weather summary used for context",
    )
    occasion: str
    total_wardrobe_items: int = Field(
        ...,
        description="Number of completed wardrobe items considered",
    )
    engine: str = Field(
        default="rule_engine",
        description="'gemini' or 'openai' if suggestions came from an LLM, 'rule_engine' for the fallback",
    )


class LookbookSection(BaseModel):
    occasion: str
    outfits: List[SuggestedOutfit]


class LookbookResponse(BaseModel):
    """Ready-made looks grouped by occasion (Outfits tab)."""
    sections: List[LookbookSection]
    weather: WeatherInfo
    total_wardrobe_items: int

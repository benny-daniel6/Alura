import uuid
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.user import UserRole


# --- User Schemas ---
class UserBase(BaseModel):
    email: EmailStr
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class UserCreate(UserBase):
    firebase_uid: str


class UserResponse(UserBase):
    # Output only: guest accounts use an undeliverable placeholder address that EmailStr would reject
    email: str
    id: uuid.UUID
    role: UserRole
    items_count: int
    tryon_credits: int
    is_public: bool
    is_guest: bool = False
    has_completed_quiz: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Style Preferences Schemas (Quiz) ---
class StylePreferencesInput(BaseModel):
    style_vibes: List[str] = Field(
        default_factory=list,
        description="Gender-neutral aesthetic vibes: minimalist, streetwear, old_money, dark_academia, avant_garde, casual_chic, retro, bohemian",
        examples=[["minimalist", "streetwear", "old_money"]]
    )
    preferred_colors: List[str] = Field(
        default_factory=list,
        description="Harmonious color palettes: monochrome, earth_tones, pastels, jewel_tones, neutrals, vibrant",
        examples=[["monochrome", "earth_tones", "neutrals"]]
    )
    avoided_colors: List[str] = Field(
        default_factory=list,
        description="Colors the user dislikes",
        examples=[["neon_yellow", "hot_pink"]]
    )
    primary_occasions: List[str] = Field(
        default_factory=list,
        description="Frequent wear occasions: office_work, casual_daily, evening_dinner, party_nightlife, formal_events, loungewear, activewear",
        examples=[["casual_daily", "office_work", "evening_dinner"]]
    )
    climate_zone: str = Field(
        default="temperate",
        description="User's primary climate or weather profile: temperate, hot_humid, cold_dry, tropical, oceanic",
        examples=["temperate"]
    )
    sizing_preference: Literal["oversized", "regular", "fitted"] = Field(
        default="regular",
        description="General silhouette cut preference",
        examples=["regular"]
    )


class StylePreferencesResponse(StylePreferencesInput):
    id: uuid.UUID
    user_id: uuid.UUID
    quiz_completed: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Auth Sync Schemas ---
class AuthSyncRequest(BaseModel):
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class DevTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    firebase_uid: str
    email: str


# --- Alura account sign-in ---
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class GoogleSignInRequest(BaseModel):
    id_token: str = Field(..., min_length=20, max_length=4096)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

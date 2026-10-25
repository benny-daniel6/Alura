from typing import List, Union
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Fail closed: dev-only behaviour (auth bypass, local storage, ML fallbacks) requires
    # ENVIRONMENT=development (or ENV=development) to be set explicitly.
    ENVIRONMENT: str = Field(default="production", validation_alias=AliasChoices("ENVIRONMENT", "ENV"))
    PROJECT_NAME: str = "Alura AI Wardrobe & Styling API"
    API_V1_STR: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/aura_db"

    # Firebase
    FIREBASE_CREDENTIALS_PATH: str = ""
    FIREBASE_PROJECT_ID: str = "aura-wardrobe-dev"
    DEV_AUTH_BYPASS: bool = False  # Only honoured when ENVIRONMENT=development

    # Alura accounts (email/password + Google): signed session tokens
    JWT_SECRET: str = ""  # required outside development; generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
    ACCESS_TOKEN_DAYS: int = 30
    # OAuth client IDs whose Google ID tokens are accepted (the app's Web client ID). Empty = Google sign-in off.
    GOOGLE_OAUTH_CLIENT_IDS: List[str] = []
    # Guest accounts not used for this many days are deleted (daily worker job)
    GUEST_RETENTION_DAYS: int = 30
    # "redis" shares rate limits across API workers; "memory" is per process (tests)
    RATE_LIMIT_BACKEND: str = "redis"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Storage
    # Local disk is used in development only; every other environment requires S3.
    S3_ENDPOINT_URL: str = ""  # Empty = AWS S3; set for MinIO / R2 etc.
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET_NAME: str = ""
    S3_REGION: str = "us-east-1"
    S3_PUBLIC_BASE_URL: str = ""  # Public URL prefix for objects; derived from endpoint/bucket if empty
    # Private bucket: API responses carry short-lived signed links instead of public URLs
    S3_SIGNED_URLS: bool = True
    S3_SIGNED_URL_SECONDS: int = 24 * 3600

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    # Google Gemini: garment studio photos, garment tagging and the AI stylist.
    # Leave the key blank to use the local models (rembg + OpenCLIP) and the rule-based stylist.
    GEMINI_API_KEY: str = ""
    GEMINI_API_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    GEMINI_TEXT_MODEL: str = "gemini-2.5-flash"
    GEMINI_IMAGE_MODEL: str = "gemini-2.5-flash-image"
    GEMINI_TIMEOUT_SECONDS: float = 90.0

    # "gemini": Gemini redraws the garment as a white-background product shot, then rembg cuts it out.
    # "local": rembg on the user's photo only. Gemini falls back to local when the key is missing or a call fails.
    GARMENT_IMAGE_PROVIDER: str = "gemini"
    # rembg model for the transparent cutout. u2net: ~0.5 s and ~1 GB RAM per worker on CPU. birefnet-general is
    # slightly cleaner on cluttered photos but ~23 s and ~8 GB on CPU (GPU only). isnet-general-use failed often in benchmarks.
    REMBG_MODEL: str = "u2net"

    # AI stylist engine: "gemini", "openai" (any OpenAI-compatible API) or "rules"
    STYLIST_PROVIDER: str = "gemini"
    LLM_API_KEY: str = ""  # OpenAI-compatible provider only
    LLM_API_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        return ["*"]

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        populate_by_name=True,
        extra="ignore"
    )


settings = Settings()

from app.core.config import Settings
from app.core.production_checks import check_production_config


def make(**kw):
    return Settings(_env_file=None, **kw)


def test_development_is_never_blocked():
    assert check_production_config(make(ENVIRONMENT="development")) == ([], [])


def test_production_requires_storage_and_sign_in(tmp_path):
    errors, _ = check_production_config(make(ENVIRONMENT="production"))
    assert any("S3" in e for e in errors) and any("Sign-in" in e for e in errors)

    creds = tmp_path / "firebase.json"
    creds.write_text("{}")
    errors, warnings = check_production_config(make(
        ENVIRONMENT="production", S3_BUCKET_NAME="b", S3_ACCESS_KEY="k", S3_SECRET_KEY="s",
        FIREBASE_CREDENTIALS_PATH=str(creds),
        DATABASE_URL="postgresql+asyncpg://aura:strong@db/aura", BACKEND_CORS_ORIGINS=["https://aura.app"],
        GEMINI_API_KEY="x", DEV_AUTH_BYPASS=False,
    ))
    assert errors == [] and warnings == []


def test_missing_credentials_file_and_risky_defaults_are_reported(tmp_path):
    errors, warnings = check_production_config(make(
        ENVIRONMENT="production", S3_BUCKET_NAME="b", S3_ACCESS_KEY="k", S3_SECRET_KEY="s",
        FIREBASE_CREDENTIALS_PATH=str(tmp_path / "missing.json"), DEV_AUTH_BYPASS=True,
    ))
    assert errors == [f"Firebase credentials file not found: {tmp_path / 'missing.json'}"]
    assert any("DEV_AUTH_BYPASS" in w for w in warnings)
    assert any("default postgres password" in w for w in warnings)

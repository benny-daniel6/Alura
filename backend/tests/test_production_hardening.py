import io
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import Settings, settings
from app.services.ml_pipeline import MLPipeline
from app.services.storage import StorageService


# ---------- Config defaults fail closed ----------

def test_settings_default_to_production_without_dev_bypass(monkeypatch):
    for var in ("ENVIRONMENT", "ENV", "DEV_AUTH_BYPASS"):
        monkeypatch.delenv(var, raising=False)
    fresh = Settings(_env_file=None)
    assert fresh.ENVIRONMENT == "production"
    assert fresh.DEV_AUTH_BYPASS is False
    assert fresh.is_development is False


def test_env_alias_enables_development(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("ENV", "development")
    assert Settings(_env_file=None).is_development is True


# ---------- Dev token bypass ----------

@pytest.mark.asyncio
async def test_dev_token_endpoint_works_in_development(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)
    response = await async_client.post("/api/v1/auth/dev-token", params={"email": "dev@aura.app"})
    assert response.status_code == 200
    assert response.json()["access_token"] == "dev-token:dev@aura.app"


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["production", "staging", ""])
async def test_dev_token_endpoint_forbidden_outside_development(async_client: AsyncClient, monkeypatch, environment):
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)  # even if someone leaves the flag on
    response = await async_client.post("/api/v1/auth/dev-token", params={"email": "attacker@external.com"})
    assert response.status_code == 403
    assert "disabled in production" in response.json()["detail"]


@pytest.mark.asyncio
async def test_dev_bearer_token_accepted_in_development(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)
    response = await async_client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer dev-token:dev@aura.app"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["dev-token:admin@aura-wardrobe.app", "test-token-123"])
async def test_dev_bearer_tokens_rejected_in_production(async_client: AsyncClient, monkeypatch, token):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)
    response = await async_client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# ---------- Local storage fallback ----------

class FakeS3Client:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[(Bucket, Key)] = (Body, ContentType)

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)][0])}

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


def _local_files(root: Path):
    return [p for p in root.rglob("*") if p.is_file()]


@pytest.mark.asyncio
async def test_local_storage_used_in_development(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    service = StorageService(local_dir=tmp_path)

    url = await service.save_file(b"png-bytes", "cutout.png", subfolder="cutouts")
    assert url == "/static/cutouts/cutout.png"
    assert (tmp_path / "cutouts" / "cutout.png").read_bytes() == b"png-bytes"
    assert await service.read_file(url) == b"png-bytes"
    assert await service.delete_file(url) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["save", "read", "delete"])
async def test_local_storage_fallback_rejected_in_production_without_s3(monkeypatch, tmp_path, operation):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "")
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "")
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "")
    (tmp_path / "cutouts").mkdir()
    (tmp_path / "cutouts" / "cutout.png").write_bytes(b"local")
    service = StorageService(local_dir=tmp_path)

    with pytest.raises(RuntimeError) as exc_info:
        if operation == "save":
            await service.save_file(b"test image data", "new.png", subfolder="cutouts")
        elif operation == "read":
            await service.read_file("/static/cutouts/cutout.png")
        else:
            await service.delete_file("/static/cutouts/cutout.png")

    assert "strictly disabled in production" in str(exc_info.value)
    assert _local_files(tmp_path) == [tmp_path / "cutouts" / "cutout.png"]  # untouched


@pytest.mark.asyncio
async def test_production_storage_uses_s3_and_never_touches_local_disk(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "aura-assets")
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "key")
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "secret")
    monkeypatch.setattr(settings, "S3_PUBLIC_BASE_URL", "https://cdn.aura.app")
    service = StorageService(local_dir=tmp_path)
    fake = FakeS3Client()
    service._s3_client = fake

    url = await service.save_file(b"png-bytes", "cutout.png", subfolder="cutouts")
    assert url == "https://cdn.aura.app/cutouts/cutout.png"
    assert fake.objects[("aura-assets", "cutouts/cutout.png")] == (b"png-bytes", "image/png")
    assert await service.read_file(url) == b"png-bytes"
    await service.delete_file(url)
    assert fake.objects == {}
    assert _local_files(tmp_path) == []

    # Local /static paths are never resolved outside development
    with pytest.raises(RuntimeError):
        await service.read_file("/static/cutouts/cutout.png")


# ---------- ML heuristic fallbacks ----------

def test_ml_fallback_allowed_only_in_development(monkeypatch):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "navy").save(buf, format="PNG")
    unloaded = MLPipeline()

    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert len(unloaded.analyze_garment(buf.getvalue())["embedding"]) == 512

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="fallbacks are disabled"):
        unloaded.remove_background(buf.getvalue())
    with pytest.raises(RuntimeError, match="fallbacks are disabled"):
        unloaded.analyze_garment(buf.getvalue())

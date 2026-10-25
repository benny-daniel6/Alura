"""Alura accounts: email/password, guest (and upgrade), Google, session tokens, signed photo URLs."""

import uuid

import pytest

import app.api.v1.endpoints.auth as auth_module
from app.core import rate_limit
from app.core.passwords import hash_password, verify_password
from app.core.tokens import create_access_token, decode_access_token


@pytest.fixture(autouse=True)
def reset_rate_limits():
    rate_limit.reset_memory()
    yield
    rate_limit.reset_memory()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


async def register(client, email="ana@example.com", password="correct horse", name="Ana"):
    return await client.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": name})


def test_password_hashing_round_trip_and_rejects_garbage():
    stored = hash_password("s3cret-pass")
    assert stored.startswith("scrypt$") and "s3cret-pass" not in stored
    assert verify_password("s3cret-pass", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("s3cret-pass", "not-a-hash")
    assert hash_password("same") != hash_password("same")  # random salt


def test_session_tokens_round_trip_and_reject_foreign_tokens():
    uid = uuid.uuid4()
    assert decode_access_token(create_access_token(uid)) == uid
    assert decode_access_token("dev-token:someone@example.com") is None
    assert decode_access_token(create_access_token(uid) + "x") is None


@pytest.mark.asyncio
async def test_register_then_use_token(async_client):
    resp = await register(async_client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user"]["email"] == "ana@example.com" and body["user"]["display_name"] == "Ana"
    assert body["user"]["is_guest"] is False and body["user"]["has_completed_quiz"] is False

    me = await async_client.get("/api/v1/users/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200 and me.json()["email"] == "ana@example.com"


@pytest.mark.asyncio
async def test_register_validation_and_duplicates(async_client):
    assert (await register(async_client, password="short")).status_code == 422
    assert (await register(async_client, email="not-an-email")).status_code == 422
    assert (await register(async_client)).status_code == 201
    dup = await register(async_client, email="ANA@Example.com")
    assert dup.status_code == 409 and "already exists" in dup.json()["detail"]


@pytest.mark.asyncio
async def test_login_success_and_uniform_failure(async_client):
    await register(async_client)
    ok = await async_client.post("/api/v1/auth/login", json={"email": "Ana@Example.com", "password": "correct horse"})
    assert ok.status_code == 200 and decode_access_token(ok.json()["access_token"]) is not None

    wrong = await async_client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "nope"})
    unknown = await async_client.post("/api/v1/auth/login", json={"email": "who@example.com", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]  # no account enumeration


@pytest.mark.asyncio
async def test_login_throttle_blocks_brute_force(async_client):
    await register(async_client)
    for _ in range(10):
        await async_client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "bad"})
    blocked = await async_client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "correct horse"})
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_guest_account_and_upgrade_keeps_data(async_client, db_session):
    guest = await async_client.post("/api/v1/auth/guest")
    assert guest.status_code == 201
    token = guest.json()["access_token"]
    assert guest.json()["user"]["is_guest"] is True

    from app.models.user import User
    from app.models.wardrobe import ProcessingStatus, WardrobeItem
    from sqlalchemy import select
    user = (await db_session.execute(select(User).where(User.is_guest.is_(True)))).scalar_one()
    db_session.add(WardrobeItem(user_id=user.id, name="Tee", original_image_url="/static/originals/x.jpg",
                                status=ProcessingStatus.COMPLETED))
    await db_session.commit()

    up = await async_client.post("/api/v1/auth/upgrade", headers=bearer(token),
                                 json={"email": "guest@example.com", "password": "new password", "display_name": "Sam"})
    assert up.status_code == 200, up.text
    assert up.json()["user"]["is_guest"] is False and up.json()["user"]["email"] == "guest@example.com"
    items = await async_client.get("/api/v1/wardrobe/items", headers=bearer(up.json()["access_token"]))
    assert [i["name"] for i in items.json()] == ["Tee"]

    login = await async_client.post("/api/v1/auth/login", json={"email": "guest@example.com", "password": "new password"})
    assert login.status_code == 200
    again = await async_client.post("/api/v1/auth/upgrade", headers=bearer(login.json()["access_token"]),
                                    json={"email": "x@example.com", "password": "another one"})
    assert again.status_code == 400


@pytest.mark.asyncio
async def test_google_sign_in(async_client, monkeypatch):
    from app.core.config import settings

    resp = await async_client.post("/api/v1/auth/google", json={"id_token": "x" * 40})
    assert resp.status_code == 503  # not configured

    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_IDS", ["web-client.apps.googleusercontent.com"])
    claims = {"sub": "google-123", "email": "Ana@Example.com", "email_verified": True, "name": "Ana G"}
    monkeypatch.setattr(auth_module, "_verify_google_id_token", lambda token: claims)

    await register(async_client)  # existing email/password account with the same email
    linked = await async_client.post("/api/v1/auth/google", json={"id_token": "x" * 40})
    assert linked.status_code == 200
    assert linked.json()["user"]["email"] == "ana@example.com"  # linked, not duplicated

    claims2 = {"sub": "google-999", "email": "new@example.com", "email_verified": True, "name": "New"}
    monkeypatch.setattr(auth_module, "_verify_google_id_token", lambda token: claims2)
    created = await async_client.post("/api/v1/auth/google", json={"id_token": "x" * 40})
    assert created.status_code == 200 and created.json()["user"]["display_name"] == "New"

    def reject(token):
        raise ValueError("bad signature")
    monkeypatch.setattr(auth_module, "_verify_google_id_token", reject)
    assert (await async_client.post("/api/v1/auth/google", json={"id_token": "x" * 40})).status_code == 401


@pytest.mark.asyncio
async def test_token_for_deleted_account_is_rejected(async_client):
    body = (await register(async_client)).json()
    assert (await async_client.delete("/api/v1/users/me/delete-data", headers=bearer(body["access_token"]))).status_code == 200
    me = await async_client.get("/api/v1/users/me", headers=bearer(body["access_token"]))
    assert me.status_code == 401


def test_photo_urls_are_signed_for_a_private_bucket(monkeypatch):
    from app.core.config import settings
    from app.services.storage import storage_service

    class FakeS3:
        def generate_presigned_url(self, op, Params, ExpiresIn):
            return f"https://signed.example/{Params['Key']}?X-Amz-Expires={ExpiresIn}"

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    for k, v in {"S3_BUCKET_NAME": "b", "S3_ACCESS_KEY": "k", "S3_SECRET_KEY": "s", "S3_REGION": "ap-south-1",
                 "S3_ENDPOINT_URL": "", "S3_PUBLIC_BASE_URL": ""}.items():
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(storage_service, "_s3_client", FakeS3())
    stored = "https://b.s3.ap-south-1.amazonaws.com/cutouts/abc.png"
    assert storage_service.client_url(stored) == "https://signed.example/cutouts/abc.png?X-Amz-Expires=86400"
    assert storage_service.client_url(None) is None

    monkeypatch.setattr(settings, "S3_SIGNED_URLS", False)
    assert storage_service.client_url(stored) == stored

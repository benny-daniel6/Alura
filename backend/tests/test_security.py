"""Security hardening: session revocation, password policy, rate limits, headers, guest clean-up, input limits."""

import io
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image
from sqlalchemy import select

from app.core import rate_limit
from app.core.tokens import create_access_token


@pytest.fixture(autouse=True)
def reset_rate_limits():
    rate_limit.reset_memory()
    yield
    rate_limit.reset_memory()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


async def register(client, email="sec@example.com", password="a sound passphrase"):
    resp = await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_password_change_revokes_other_sessions(async_client, monkeypatch):
    import app.core.tokens as tokens
    # The "other device" session was issued 10 s ago (tokens carry whole-second issue times)
    earlier = type("Earlier", (), {"now": staticmethod(lambda tz=None: datetime.now(timezone.utc) - timedelta(seconds=10))})
    monkeypatch.setattr(tokens, "datetime", earlier)
    old = await register(async_client)
    monkeypatch.setattr(tokens, "datetime", datetime)

    wrong = await async_client.post("/api/v1/auth/password", headers=bearer(old),
                                    json={"current_password": "nope", "new_password": "another good phrase"})
    assert wrong.status_code == 400

    changed = await async_client.post("/api/v1/auth/password", headers=bearer(old),
                                      json={"current_password": "a sound passphrase", "new_password": "another good phrase"})
    assert changed.status_code == 200, changed.text
    new = changed.json()["access_token"]

    assert (await async_client.get("/api/v1/users/me", headers=bearer(old))).status_code == 401
    assert (await async_client.get("/api/v1/users/me", headers=bearer(new))).status_code == 200
    login = await async_client.post("/api/v1/auth/login", json={"email": "sec@example.com", "password": "another good phrase"})
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_logout_all_rejects_earlier_tokens(async_client, db_session):
    token = await register(async_client)
    from app.models.user import User
    user = (await db_session.execute(select(User).where(User.email == "sec@example.com"))).scalar_one()
    stale = create_access_token(user.id)
    user.tokens_valid_after = datetime.now(timezone.utc) + timedelta(seconds=2)
    await db_session.commit()
    assert (await async_client.get("/api/v1/users/me", headers=bearer(stale))).status_code == 401
    assert (await async_client.post("/api/v1/auth/logout-all", headers=bearer(token))).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("password", ["password123", "12345678", "aaaaaaaaaa", "sec@example.com"])
async def test_weak_passwords_are_rejected(async_client, password):
    resp = await async_client.post("/api/v1/auth/register", json={"email": "sec@example.com", "password": password})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_signup_and_guest_creation_are_rate_limited_per_network(async_client):
    for n in range(10):
        assert (await async_client.post("/api/v1/auth/register",
                                        json={"email": f"u{n}@example.com", "password": "a sound passphrase"})).status_code == 201
    over = await async_client.post("/api/v1/auth/register", json={"email": "u99@example.com", "password": "a sound passphrase"})
    assert over.status_code == 429

    for _ in range(20):
        assert (await async_client.post("/api/v1/auth/guest")).status_code == 201
    assert (await async_client.post("/api/v1/auth/guest")).status_code == 429


@pytest.mark.asyncio
async def test_uploads_are_rate_limited_per_user(async_client, monkeypatch):
    import app.api.v1.endpoints.wardrobe as wardrobe_module
    monkeypatch.setattr(rate_limit.uploads, "limit", 2)

    async def no_pool():
        return None

    async def skip_inline(*args, **kwargs):
        return None
    monkeypatch.setattr(wardrobe_module, "get_arq_pool", no_pool)
    monkeypatch.setattr(wardrobe_module, "process_wardrobe_item", skip_inline)
    token = await register(async_client)
    buf = io.BytesIO()
    Image.new("RGB", (120, 120), "navy").save(buf, format="JPEG")
    statuses = []
    for _ in range(3):
        r = await async_client.post("/api/v1/wardrobe/items/upload", headers=bearer(token),
                                    files={"file": ("a.jpg", buf.getvalue(), "image/jpeg")})
        statuses.append(r.status_code)
    assert statuses == [202, 202, 429]


@pytest.mark.asyncio
async def test_decompression_bomb_is_rejected_without_details(async_client, monkeypatch):
    import app.api.v1.endpoints.wardrobe as wardrobe_module
    token = await register(async_client)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # a 120x120 test image now counts as a "bomb"
    buf = io.BytesIO()
    Image.new("RGB", (120, 120), "red").save(buf, format="PNG")
    r = await async_client.post("/api/v1/wardrobe/items/upload", headers=bearer(token),
                                files={"file": ("bomb.png", buf.getvalue(), "image/png")})
    assert r.status_code == 400
    assert "Decompression" not in r.text and "pixels" not in r.text  # no internal error details


@pytest.mark.asyncio
async def test_security_headers_and_no_credentialed_cors(async_client):
    r = await async_client.get("/health", headers={"Origin": "https://evil.example"})
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers.get("access-control-allow-credentials") != "true"

    token = await register(async_client)
    me = await async_client.get("/api/v1/users/me", headers=bearer(token))
    assert me.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_input_length_limits(async_client):
    token = await register(async_client)
    r = await async_client.get("/api/v1/wardrobe/items", headers=bearer(token), params={"search": "x" * 101})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_stale_guests_are_purged_but_active_guests_and_members_kept(async_client, db_session):
    from app.models.user import User
    from app.services.account_purge import purge_stale_guests

    stale_guest = (await async_client.post("/api/v1/auth/guest")).json()["user"]["id"]
    active_guest = (await async_client.post("/api/v1/auth/guest")).json()["user"]["id"]
    await register(async_client)

    users = {str(u.id): u for u in (await db_session.execute(select(User))).scalars().all()}
    users[stale_guest].last_seen_at = datetime.now(timezone.utc) - timedelta(days=45)
    await db_session.commit()

    assert await purge_stale_guests(db_session, retention_days=30) == 1
    remaining = {str(u.id) for u in (await db_session.execute(select(User))).scalars().all()}
    assert stale_guest not in remaining and active_guest in remaining and len(remaining) == 2


@pytest.mark.asyncio
async def test_last_seen_is_recorded(async_client, db_session):
    from app.models.user import User
    token = await register(async_client)
    await async_client.get("/api/v1/users/me", headers=bearer(token))
    user = (await db_session.execute(select(User).where(User.email == "sec@example.com"))).scalar_one()
    await db_session.refresh(user)
    assert user.last_seen_at is not None


@pytest.mark.asyncio
async def test_login_runs_a_hash_check_even_for_unknown_emails(async_client, monkeypatch):
    import app.api.v1.endpoints.auth as auth_module
    calls = []
    real = auth_module.verify_password
    monkeypatch.setattr(auth_module, "verify_password", lambda p, h: calls.append(h) or real(p, h))
    await async_client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever pw"})
    assert calls == [auth_module._DUMMY_PASSWORD_HASH]

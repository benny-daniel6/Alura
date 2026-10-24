import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "Alura Wardrobe API" in data["service"]


@pytest.mark.asyncio
async def test_unauthorized_access(async_client: AsyncClient):
    # Without bearer token, should return 401
    response = await async_client.get("/api/v1/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dev_token_generation(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/dev-token",
        params={"email": "alex.style@aura.internal"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["access_token"].startswith("dev-token:alex.style@aura.internal")


@pytest.mark.asyncio
async def test_auth_sync_and_onboarding_quiz_flow(async_client: AsyncClient):
    user_email = "taylor.curator@aura-wardrobe.app"
    headers = {"Authorization": f"Bearer dev-token:{user_email}"}

    # 1. Sync User via Auth Sync
    sync_resp = await async_client.post(
        "/api/v1/auth/sync",
        headers=headers,
        json={"display_name": "Taylor C.", "avatar_url": "https://images.aura.internal/avatar1.jpg"}
    )
    assert sync_resp.status_code == 200
    user_data = sync_resp.json()
    assert user_data["email"] == user_email
    assert user_data["display_name"] == "Taylor C."
    assert user_data["role"] == "free"
    assert user_data["items_count"] == 0
    assert user_data["tryon_credits"] == 3
    assert user_data["has_completed_quiz"] is False

    # 2. Verify Profile Endpoint
    me_resp = await async_client.get("/api/v1/users/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["id"] == user_data["id"]

    # 3. Check Initial Preferences
    pref_get_resp = await async_client.get("/api/v1/users/me/preferences", headers=headers)
    assert pref_get_resp.status_code == 200
    assert pref_get_resp.json()["quiz_completed"] is False

    # 4. Submit Style Preferences Quiz (Milestone 1 Core)
    quiz_submission = {
        "style_vibes": ["minimalist", "streetwear", "quiet_luxury"],
        "preferred_colors": ["monochrome", "earth_tones", "sage"],
        "avoided_colors": ["neon_yellow"],
        "primary_occasions": ["office_work", "casual_daily", "evening_dinner"],
        "climate_zone": "temperate",
        "sizing_preference": "regular"
    }

    submit_resp = await async_client.put(
        "/api/v1/users/me/preferences",
        headers=headers,
        json=quiz_submission
    )
    assert submit_resp.status_code == 200
    pref_saved = submit_resp.json()
    assert pref_saved["quiz_completed"] is True
    assert "quiet_luxury" in pref_saved["style_vibes"]
    assert "earth_tones" in pref_saved["preferred_colors"]
    assert "office_work" in pref_saved["primary_occasions"]

    # 5. Verify User Profile Now Shows quiz_completed = True
    me_after_quiz = await async_client.get("/api/v1/users/me", headers=headers)
    assert me_after_quiz.status_code == 200
    assert me_after_quiz.json()["has_completed_quiz"] is True

    # 6. Test Privacy & GDPR Delete-My-Data Endpoint
    delete_resp = await async_client.delete("/api/v1/users/me/delete-data", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["success"] is True

    # Verify user record is deleted
    # In next call, token would re-provision a fresh new user with uncompleted quiz
    sync_again = await async_client.post("/api/v1/auth/sync", headers=headers)
    assert sync_again.status_code == 200
    assert sync_again.json()["has_completed_quiz"] is False

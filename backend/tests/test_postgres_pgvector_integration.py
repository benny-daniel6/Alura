"""
Integration tests against the real Postgres+pgvector container (docker compose up -d db redis).

No mocks in the ML path: a real garment photo is uploaded through the API, enqueued on real Redis,
picked up by a real ARQ worker (whose startup loads rembg + OpenCLIP), and the resulting cutout,
512-dim pgvector embedding and HNSW index are asserted on in Postgres.

Skipped when Postgres/Redis are unreachable; set REQUIRE_INTEGRATION=1 (e.g. in CI) to fail instead.
"""
import asyncio
import io
import os
import random
import signal
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.api.v1.endpoints.wardrobe as wardrobe_endpoint
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app as fastapi_app
from app.models.user import User, UserRole
from app.models.wardrobe import WardrobeItem, ProcessingStatus
from app.services.similarity import find_similar_items
from app.services.storage import storage_service
from app.workers.arq_worker import WorkerSettings, startup, shutdown

PG_TEST_URL = os.environ.get(
    "TEST_POSTGRES_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/aura_test"
)
REDIS_TEST_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "garments"
HNSW_INDEX = "ix_wardrobe_items_clip_embedding_hnsw"


def _unavailable(reason: str):
    if os.environ.get("REQUIRE_INTEGRATION"):
        pytest.fail(reason)
    pytest.skip(reason)


async def _ensure_test_database() -> None:
    import asyncpg
    url = make_url(PG_TEST_URL)
    conn = await asyncpg.connect(
        user=url.username, password=url.password, host=url.host, port=url.port or 5432,
        database="postgres", timeout=3,
    )
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database):
            await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def pg_sessions():
    try:
        await _ensure_test_database()
    except Exception as e:
        _unavailable(f"Postgres+pgvector not reachable for {PG_TEST_URL} ({e}). Run: docker compose up -d db")

    engine = create_async_engine(PG_TEST_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_client(pg_sessions, monkeypatch, tmp_path):
    """API wired to the Postgres test database, dev auth, and tmp local storage."""
    async def override_get_db():
        async with pg_sessions() as session:
            yield session

    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "DEV_AUTH_BYPASS", True)
    monkeypatch.setattr(storage_service, "local_dir", tmp_path)
    fastapi_app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
        yield client
    fastapi_app.dependency_overrides.clear()


async def create_user(sessions, email: str, items_count: int = 0, role=UserRole.FREE) -> dict:
    async with sessions() as db:
        user = User(
            firebase_uid=f"mock-firebase-{email.replace('@', '-at-')}",  # matches dev-token resolution
            email=email, role=role, items_count=items_count,
        )
        db.add(user)
        await db.commit()
        return {"id": user.id, "headers": {"Authorization": f"Bearer dev-token:{email}"}}


def garment_photos():
    photos = sorted(p for p in FIXTURE_DIR.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    assert photos, f"No garment photos found in {FIXTURE_DIR}"
    return photos


# ---------------------------------------------------------------------------
# 1. Upload -> Redis -> real ARQ worker (rembg + OpenCLIP) -> pgvector -> HNSW search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_real_upload_worker_cutout_embedding_and_hnsw_search(pg_sessions, pg_client, monkeypatch):
    from arq.connections import RedisSettings, create_pool
    from arq.worker import Worker

    redis_settings = RedisSettings.from_dsn(REDIS_TEST_URL)
    try:
        redis = await create_pool(redis_settings)
        await redis.flushdb()
        await redis.aclose()
    except Exception as e:
        _unavailable(f"Redis not reachable at {REDIS_TEST_URL} ({e}). Run: docker compose up -d redis")
    monkeypatch.setattr(settings, "REDIS_URL", REDIS_TEST_URL)
    if not hasattr(signal, "SIGUSR1"):
        # arq's Worker.close() references SIGUSR1, which Windows lacks; it is only used for logging/cancel
        monkeypatch.setattr(signal, "SIGUSR1", signal.SIGTERM, raising=False)

    user = await create_user(pg_sessions, "integration@aura.app")
    photo = garment_photos()[0]
    original = Image.open(photo)

    # --- Upload through the real API; it enqueues on real Redis ---
    resp = await pg_client.post(
        "/api/v1/wardrobe/items/upload",
        headers=user["headers"],
        files={"file": (photo.name, photo.read_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 202, resp.text
    item_id = uuid.UUID(resp.json()["item_id"])

    # --- Run the real ARQ worker in burst mode until the queue is drained ---
    worker = Worker(
        functions=WorkerSettings.functions,
        on_startup=startup,
        on_shutdown=shutdown,
        redis_settings=redis_settings,
        ctx={"session_factory": pg_sessions},
        burst=True,
        handle_signals=False,
        job_timeout=600,
        max_tries=1,
    )
    try:
        await worker.main()
    finally:
        await worker.close()
    assert worker.jobs_complete == 1 and worker.jobs_failed == 0

    pipeline = worker.ctx["ml_pipeline"]
    assert pipeline.rembg_session is not None, "rembg model did not load; the test would be exercising fallbacks"
    assert pipeline.clip_model is not None, "OpenCLIP model did not load; the test would be exercising fallbacks"

    async with pg_sessions() as db:
        item = (await db.execute(select(WardrobeItem).where(WardrobeItem.id == item_id))).scalar_one()
        assert item.status == ProcessingStatus.COMPLETED, item.error_message
        assert item.cutout_image_url and item.thumbnail_url

        # --- Cutout: a real segmentation has both fully transparent and fully opaque regions ---
        cutout = Image.open(io.BytesIO(await storage_service.read_file(item.cutout_image_url)))
        assert cutout.mode == "RGBA"
        assert cutout.size == original.size
        alpha = cutout.getchannel("A")
        histogram = alpha.histogram()
        total = cutout.width * cutout.height
        # u2net emits soft alpha (garment ~254), so "opaque" means >= 200
        transparent, opaque = histogram[0] / total, sum(histogram[200:]) / total
        assert transparent > 0.15, f"only {transparent:.1%} background removed"
        assert opaque > 0.25, f"only {opaque:.1%} of garment kept"
        # The grey backdrop corner must be gone, the garment centre kept
        assert alpha.getpixel((5, 5)) == 0
        assert alpha.getpixel((cutout.width // 2, cutout.height // 2)) >= 200

        # --- Embedding: stored as a real 512-dim pgvector, unit-normalised, not the dev fallback ---
        dims, norm = (await db.execute(
            text("SELECT vector_dims(clip_embedding), vector_norm(clip_embedding) FROM wardrobe_items WHERE id = :id"),
            {"id": item_id},
        )).one()
        assert dims == 512
        assert abs(norm - 1.0) < 1e-3
        embedding = [float(v) for v in item.clip_embedding]  # pgvector returns a numpy array
        assert sum(1 for v in embedding if abs(v) > 1e-6) > 400  # fallback vector is one-hot

        # --- HNSW: index exists on the real table and the planner uses it for <=> ordering ---
        indexdef = (await db.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"), {"name": HNSW_INDEX}
        )).scalar_one()
        assert "USING hnsw" in indexdef and "vector_cosine_ops" in indexdef

        # Add distractor items so the search is non-trivial
        rng = random.Random(42)
        for i in range(60):
            vec = [rng.gauss(0, 1) for _ in range(512)]
            n = sum(v * v for v in vec) ** 0.5
            db.add(WardrobeItem(
                user_id=user["id"], name=f"distractor-{i}", original_image_url=f"/static/originals/d{i}.jpg",
                status=ProcessingStatus.COMPLETED, clip_embedding=[v / n for v in vec],
            ))
        await db.commit()

        vec_literal = "[" + ",".join(repr(v) for v in embedding) + "]"
        await db.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(row[0] for row in (await db.execute(
            text("EXPLAIN SELECT id FROM wardrobe_items ORDER BY clip_embedding <=> CAST(:v AS vector) LIMIT 5"),
            {"v": vec_literal},
        )).all())
        assert HNSW_INDEX in plan, plan
        await db.rollback()

        # The service compiles to the cosine operator that the index serves
        compiled = str(
            select(WardrobeItem.id)
            .order_by(WardrobeItem.clip_embedding.cosine_distance(embedding))
            .compile(dialect=postgresql.dialect())
        )
        assert "<=>" in compiled

        matches = await find_similar_items(db, user["id"], embedding, limit=5)
        assert matches[0][0].id == item_id
        assert matches[0][1] < 1e-4
        assert all(d > 0.3 for _, d in matches[1:])  # random distractors are far away

    # --- And through the public API ---
    similar = await pg_client.get(f"/api/v1/wardrobe/items/{item_id}/similar?limit=3", headers=user["headers"])
    assert similar.status_code == 200
    assert len(similar.json()) == 3
    assert all(r["item"]["id"] != str(item_id) for r in similar.json())


# ---------------------------------------------------------------------------
# 2. Quota is atomic under concurrent uploads (row lock + fresh read)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_uploads_cannot_exceed_free_tier_quota(pg_sessions, pg_client, monkeypatch):
    async def no_pool():
        return None

    async def no_processing(ctx, item_id):
        return None

    # This test is about the upload transaction; ML processing is covered above.
    monkeypatch.setattr(wardrobe_endpoint, "get_arq_pool", no_pool)
    monkeypatch.setattr(wardrobe_endpoint, "process_wardrobe_item", no_processing)

    user = await create_user(pg_sessions, "racer@aura.app", items_count=147)
    buf = io.BytesIO()
    Image.new("RGB", (120, 120), "navy").save(buf, format="JPEG")
    payload = buf.getvalue()

    async def upload(i):
        return await pg_client.post(
            "/api/v1/wardrobe/items/upload",
            headers=user["headers"],
            files={"file": (f"r{i}.jpg", payload, "image/jpeg")},
        )

    responses = await asyncio.gather(*(upload(i) for i in range(8)))
    codes = sorted(r.status_code for r in responses)
    assert codes == [202] * 3 + [403] * 5, codes

    async with pg_sessions() as db:
        count = (await db.execute(select(User.items_count).where(User.id == user["id"]))).scalar_one()
        rows = (await db.execute(
            select(WardrobeItem.id).where(WardrobeItem.user_id == user["id"])
        )).scalars().all()
    assert count == 150
    assert len(rows) == 3

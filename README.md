# Alura — Intelligent Digital Wardrobe & AI Stylist

> **Alura** is an original AI-powered wardrobe digitisation, daily styling, and outfit sharing platform.
> Designed with a high-fashion digital editorial aesthetic, combining computer vision foreground isolation, CLIP vector embeddings, and LLM-powered outfit generation.

---

> **Deploying?** See [DEPLOYMENT.md](DEPLOYMENT.md) (production Docker stack with HTTPS, migrations, Android release builds).
> **Benchmarks:** [backend/benchmarks/README.md](backend/benchmarks/README.md).

## Architecture & Technology Stack

- **Mobile (Android/iOS):** Flutter 3.x (Single codebase, Riverpod state management, Dio HTTP client, custom high-fashion dark editorial theme).
- **Backend API:** FastAPI (Python 3.12, async SQLAlchemy 2.0 with asyncpg, Pydantic v2).
- **Database & Search:** PostgreSQL 16 with `pgvector` extension for 512-dim OpenCLIP embedding vector similarity search via HNSW.
- **Task Queue & Cache:** Redis 7 + background workers for heavy ML inference.
- **Asset Storage:** MinIO / AWS S3 / Cloudflare R2 object storage for original photos and transparent cutout PNGs.
- **Authentication:** Firebase Auth (JWT verified with `firebase-admin` + dev bypass mode for friction-free local dev).
- **ML Pipeline:** `rembg` (ISNet/U2Net) foreground isolation + `OpenCLIP ViT-B/32` zero-shot classification and embedding generation.
- **AI Stylist:** LLM structured JSON output engine conditioned on real-time weather and personal wardrobe inventory.

---

## Project Structure

```
├── ARCHITECTURE.md          # Complete system architecture & PostgreSQL DDL schema with pgvector
├── BUILD_PLAN.md            # 4-week agile roadmap for a solo engineer
├── openapi.yaml             # Complete OpenAPI 3.1 REST specification
├── docker-compose.yml       # Local development containers (Postgres 16 + pgvector, MinIO, Redis, API, worker)
├── docker-compose.prod.yml  # Production stack (Postgres, Redis, API, ML worker, Caddy HTTPS)
├── DEPLOYMENT.md            # How to deploy the backend and ship the Android app
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI application entrypoint with CORS & health check
│   │   ├── api/v1/          # Endpoints for Auth, Users, Wardrobe, Stylist, etc.
│   │   ├── core/            # Config, Security, and Firebase JWT token validation
│   │   ├── db/              # Async SQLAlchemy session and base models
│   │   ├── models/          # Relational & Vector DB entities (User, UserPreference, etc.)
│   │   └── schemas/         # Pydantic v2 validation models
│   ├── tests/               # Pytest suite with in-memory async SQLite
│   ├── requirements.txt     # Python backend dependencies
│   └── Dockerfile
└── mobile/
    ├── pubspec.yaml         # Flutter dependencies
    └── lib/
        ├── core/            # Theme, network client, and constants
        └── features/
            ├── auth/        # Firebase Auth + Dev token bypass screen
            ├── onboarding/  # 4-step interactive Style Preferences Quiz
            └── home/        # Dashboard shell with quota tracking & GDPR data purge
```

---

## Milestone Deliverables

### Milestone 1: Authentication & Onboarding
- **FastAPI Auth & Preferences:** Firebase JWT Bearer token authentication dependency with local dev bypass mode, user profile sync, and 4-step onboarding style preferences quiz.
- **Flutter Editorial Client:** Obsidian theme with Outfit & Plus Jakarta Sans typography, auth screen with Google and local dev access, and interactive 4-step quiz.
- **Privacy & GDPR:** Hard data purge endpoint permanently deleting all user data and assets upon request.

### Milestone 2: Digital Wardrobe & Isolated ML Worker (rembg + OpenCLIP)
- **Isolated ARQ + Redis Worker Container:** High-throughput async job queue decoupling mobile uploads from heavy ML inference.
  - Preloads `rembg` (U2Net/ISNet) and `OpenCLIP` (`ViT-B/32`) once at worker startup into memory.
  - Retries with backoff (`max_tries = 3`, `job_timeout = 120s`).
  - Resilient error handling: writes unrecoverable failures to `status = 'failed'` and `error_message` in DB instead of crashing.
- **API Pipeline:**
  - `POST /api/v1/wardrobe/items/upload`: Validates max 10MB image size and client compression, enforces 150-item free tier quota, saves raw image, enqueues ARQ job, and returns HTTP 202 with `item_id` and `job_id`.
  - `GET /api/v1/wardrobe/items/{id}/status`: Polling endpoint returning status (`pending`, `processing`, `completed`, `failed`), error message, and full item metadata once ready.
  - `GET /api/v1/wardrobe/items`: Filter by category, season, favorite, and search text.
  - `PATCH /api/v1/wardrobe/items/{id}`: Manual tag editing to correct or customize AI classifications.
  - `DELETE /api/v1/wardrobe/items/{id}`: Deletes item and removes storage assets.
- **Mobile Digital Closet:**
  - `WardrobeScreen`: Staggered grid of transparent garment cutouts with category filters.
  - `UploadFlowModal`: Client-side compression check + animated real-time stepper polling job status.
  - `ItemDetailDialog`: High-fashion cutout preview with AI-detected tags and manual tag editing form.

---

## Quickstart Guide

### 1. Running Backend Locally

```bash
# Navigate to backend directory
cd backend

# Create virtual environment & install dependencies
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt

# Local config: the app defaults to ENVIRONMENT=production (no dev-token auth, no local
# storage, no ML fallbacks). Copy the example to opt into development mode.
cp .env.example .env

# Run automated tests (SQLite unit tests + Postgres/pgvector integration tests)
docker compose -f ../docker-compose.yml up -d db redis
python -m pytest tests -v
# The integration tests skip if Postgres/Redis are down; make that a failure in CI:
#   REQUIRE_INTEGRATION=1 python -m pytest tests -v

# Compare rembg models (u2net, isnet-general-use, u2net_cloth_seg) on your own photos
python scripts/compare_rembg_models.py --input-dir ../data/samples/input --output-dir ../data/samples/comparisons

# Run FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive API documentation will be accessible at:
- Swagger UI: `http://localhost:8000/api/v1/docs`
- ReDoc: `http://localhost:8000/api/v1/redoc`
- Health check: `http://localhost:8000/health`

### 2. Running with Docker Compose

To spin up the entire backend stack including PostgreSQL 16 (with pgvector), MinIO, and Redis:

```bash
docker-compose up -d
```

### 3. Running Mobile App (Flutter)

```bash
cd mobile

# Fetch Flutter dependencies
flutter pub get

# Run on connected device or emulator (Android / iOS / Chrome)
flutter run
```

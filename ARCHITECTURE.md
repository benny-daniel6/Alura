# Architecture & Technical Specification: Alura AI Wardrobe & Styling

**Brand Name:** **Alura** (Tagline: *The Intelligent Digital Wardrobe & AI Stylist*)  
**Design Persona:** High-fashion digital editorial, sleek obsidian `#0A0A0C`, warm stone `#18181B`, pearl `#F4F4F6`, accented with subtle champagne gold `#D4AF37` and electric iris `#7C6EE6`.

---

## 1. Stack Confirmation & Infrastructure

| Layer | Component | Technology | Rationale |
|---|---|---|---|
| **Mobile App** | Cross-platform | **Flutter 3.x** (Android-first, iOS ready) | 60+ FPS canvas rendering for outfit drag-and-drop, rich micro-animations, single codebase. |
| **Backend API** | Async REST API | **FastAPI (Python 3.12)** | Native async, high throughput, direct Python integration with ML libraries (rembg, open_clip, PyTorch). |
| **Primary Database** | Relational + Vectors | **PostgreSQL 16 + pgvector** | Unified store for relational wardrobe/user data + 512-dim CLIP embeddings indexed with HNSW for sub-10ms similarity search. |
| **Object Storage** | Asset Blob Store | **S3-compatible (MinIO / Cloudflare R2 / AWS S3)** | High scalability for original photos, transparent cutout PNGs, and outfit renders. |
| **Task Queue** | Background ML Jobs | **Redis + Celery / ARQ** | Decouples mobile upload response from heavy ML inference (rembg background removal + CLIP embeddings). |
| **Auth** | Identity Provider | **Firebase Auth** | Client-side Google & Email SDKs; verified server-side with `firebase-admin` JWT verification. |
| **ML Engine** | Vision & Embeddings | **rembg (ISNet/U2Net) + OpenCLIP ViT-B/32** | Instant foreground cutout and zero-shot category/color tagging + cosine vector search. |
| **Stylist LLM** | Recommendations | **OpenAI GPT-4o-mini / Gemini Flash** | Structured JSON schema generation conditioned on wardrobe items, local weather, and occasion tags. |

---

## 2. Monorepo Folder Structure

```
aura-wardrobe/
├── .gitignore
├── README.md
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── router.py
│   │   │       └── endpoints/
│   │   │           ├── auth.py
│   │   │           ├── users.py
│   │   │           ├── wardrobe.py
│   │   │           ├── outfits.py
│   │   │           ├── stylist.py
│   │   │           ├── calendar.py
│   │   │           └── social.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── exceptions.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   └── session.py
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── wardrobe.py
│   │   │   ├── outfit.py
│   │   │   ├── calendar.py
│   │   │   └── social.py
│   │   ├── schemas/
│   │   │   ├── user.py
│   │   │   ├── wardrobe.py
│   │   │   ├── outfit.py
│   │   │   ├── stylist.py
│   │   │   └── social.py
│   │   ├── services/
│   │   │   ├── storage.py
│   │   │   ├── ml_pipeline.py
│   │   │   └── llm_stylist.py
│   │   └── workers/
│   │       └── tasks.py
│   └── tests/
│       ├── conftest.py
│       ├── test_auth.py
│       └── test_users.py
└── mobile/
    ├── pubspec.yaml
    ├── assets/
    │   ├── icons/
    │   └── images/
    └── lib/
        ├── main.dart
        ├── core/
        │   ├── constants/
        │   │   └── api_constants.dart
        │   ├── network/
        │   │   └── api_client.dart
        │   └── theme/
        │       └── app_theme.dart
        └── features/
            ├── auth/
            │   ├── data/
            │   │   └── auth_repository.dart
            │   └── presentation/
            │       ├── auth_screen.dart
            │       └── controllers/
            ├── onboarding/
            │   ├── data/
            │   │   └── quiz_state.dart
            │   └── presentation/
            │       └── quiz_screen.dart
            ├── wardrobe/
            ├── outfits/
            ├── stylist/
            ├── calendar/
            └── social/
```

---

## 3. PostgreSQL Database Schema (with pgvector)

```sql
-- Enable vector extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Enum Types
CREATE TYPE user_role AS ENUM ('free', 'premium', 'admin');
CREATE TYPE clothing_category AS ENUM (
    'top', 'bottom', 'outerwear', 'dress', 'footwear', 
    'bag', 'accessory', 'headwear', 'one_piece'
);
CREATE TYPE season_type AS ENUM ('spring', 'summer', 'fall', 'winter', 'all_season');
CREATE TYPE processing_status AS ENUM ('pending', 'processing', 'completed', 'failed');
CREATE TYPE challenge_status AS ENUM ('upcoming', 'active', 'voting', 'completed');

-- 1. Users Table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    firebase_uid VARCHAR(128) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(100),
    avatar_url TEXT,
    role user_role DEFAULT 'free' NOT NULL,
    items_count INT DEFAULT 0 NOT NULL,
    tryon_credits INT DEFAULT 3 NOT NULL,
    is_public BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_users_firebase_uid ON users(firebase_uid);
CREATE INDEX idx_users_email ON users(email);

-- 2. User Style Preferences (Quiz Results)
CREATE TABLE user_preferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    style_vibes TEXT[] DEFAULT '{}', -- e.g. ['minimalist', 'streetwear', 'old_money']
    preferred_colors TEXT[] DEFAULT '{}', -- e.g. ['monochrome', 'earth_tones', 'sage']
    avoided_colors TEXT[] DEFAULT '{}',
    primary_occasions TEXT[] DEFAULT '{}', -- e.g. ['office', 'casual_daily', 'night_out']
    climate_zone VARCHAR(50) DEFAULT 'temperate',
    sizing_preference VARCHAR(50) DEFAULT 'regular', -- 'oversized', 'fitted', 'regular'
    quiz_completed BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- 3. Wardrobe Items Table
CREATE TABLE wardrobe_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(150),
    category clothing_category NOT NULL,
    sub_category VARCHAR(100), -- e.g. 'linen button-down', 'wide-leg trousers'
    primary_color VARCHAR(50),
    secondary_color VARCHAR(50),
    seasons season_type[] DEFAULT '{all_season}',
    occasions TEXT[] DEFAULT '{}',
    brand VARCHAR(100),
    size VARCHAR(30),
    original_image_url TEXT NOT NULL,
    cutout_image_url TEXT, -- Transformed transparent PNG
    thumbnail_url TEXT,
    clip_embedding vector(512), -- OpenCLIP ViT-B/32 embedding
    status processing_status DEFAULT 'pending' NOT NULL,
    is_favorite BOOLEAN DEFAULT FALSE NOT NULL,
    wear_count INT DEFAULT 0 NOT NULL,
    last_worn_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_wardrobe_user ON wardrobe_items(user_id);
CREATE INDEX idx_wardrobe_category ON wardrobe_items(category);
-- HNSW index for high performance vector similarity search (cosine distance)
CREATE INDEX idx_wardrobe_embedding ON wardrobe_items 
USING hnsw (clip_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 4. Outfits Table
CREATE TABLE outfits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(150),
    description TEXT,
    occasions TEXT[] DEFAULT '{}',
    season season_type DEFAULT 'all_season',
    canvas_state JSONB, -- Coordinates & scale of items on canvas {items: [{id, x, y, scale, rotation, zIndex}]}
    preview_image_url TEXT, -- Flattened canvas snapshot
    is_favorite BOOLEAN DEFAULT FALSE NOT NULL,
    is_public BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
CREATE INDEX idx_outfits_user ON outfits(user_id);

-- 5. Outfit Items Join Table
CREATE TABLE outfit_items (
    outfit_id UUID NOT NULL REFERENCES outfits(id) ON DELETE CASCADE,
    item_id UUID NOT NULL REFERENCES wardrobe_items(id) ON DELETE RESTRICT,
    z_index INT DEFAULT 0 NOT NULL,
    PRIMARY KEY (outfit_id, item_id)
);

-- 6. Outfit Calendar Table
CREATE TABLE calendar_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    outfit_id UUID NOT NULL REFERENCES outfits(id) ON DELETE CASCADE,
    scheduled_date DATE NOT NULL,
    notes TEXT,
    weather_summary JSONB, -- e.g. {"temp_c": 18, "condition": "Cloudy"}
    worn BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    UNIQUE(user_id, scheduled_date, outfit_id)
);
CREATE INDEX idx_calendar_user_date ON calendar_entries(user_id, scheduled_date);

-- 7. Social & Fit Challenge Tables
CREATE TABLE challenges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(150) NOT NULL,
    theme VARCHAR(150) NOT NULL, -- e.g. "Monochrome Monday", "90s Retro Minimal"
    description TEXT,
    banner_url TEXT,
    status challenge_status DEFAULT 'upcoming' NOT NULL,
    starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ends_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE TABLE challenge_submissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    challenge_id UUID NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    outfit_id UUID NOT NULL REFERENCES outfits(id) ON DELETE CASCADE,
    caption TEXT,
    upvotes_count INT DEFAULT 0 NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    UNIQUE(challenge_id, user_id)
);

CREATE TABLE social_follows (
    follower_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    following_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    PRIMARY KEY (follower_id, following_id)
);

CREATE TABLE outfit_likes (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    outfit_id UUID NOT NULL REFERENCES outfits(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    PRIMARY KEY (user_id, outfit_id)
);
```

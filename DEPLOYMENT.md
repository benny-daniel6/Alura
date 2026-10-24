# Deploying Alura

Two parts: the **backend** (API, ML worker, Postgres + pgvector, Redis) on a server, and the **Android app** built against that server's HTTPS address.

## Before launch: open items

| Item | Status | What's needed |
|---|---|---|
| **Sign-in** | Not built. The app has a developer login in debug builds only; release builds show "Sign-in is coming soon". | Choose a provider. The backend already verifies Firebase ID tokens. |
| Photo storage | Ready | An S3-compatible bucket (AWS S3, Cloudflare R2, ...). |
| AI (Gemini) | Optional | `GEMINI_API_KEY` for studio photos and the AI stylist. Without it, local models and the rule-based stylist are used. |
| Privacy policy | Not written | Required by Google Play. It must mention that photos are stored on your server and, with Gemini enabled, sent to Google. |

## 1. Backend on a VPS (Docker)

**Server:** about 4 GB RAM and 2 vCPU. The ML worker uses about 2 GB.

1. Point a DNS name (e.g. `api.example.com`) at the server, and open ports 80 and 443.
2. Copy the repository to the server, then:
   ```bash
   cp backend/.env.production.example backend/.env.production   # fill in S3, Firebase, Gemini
   mkdir -p secrets && cp /path/to/firebase-service-account.json secrets/
   export DOMAIN=api.example.com POSTGRES_PASSWORD='a-long-random-password'
   docker compose -f docker-compose.prod.yml up -d --build
   ```
3. Check that it's running: `curl https://api.example.com/health` should return `"environment": "production"`.

What happens on start:
- **Caddy** gets an HTTPS certificate automatically.
- **The API applies database migrations** (`alembic upgrade head`) and then starts.
- **The worker waits for the API to be healthy** before taking jobs.

If something essential is missing (storage keys, the sign-in credentials file), the API refuses to start and logs exactly what to fix: `docker compose -f docker-compose.prod.yml logs api`.

**Updating:** `git pull && docker compose -f docker-compose.prod.yml up -d --build`. Migrations run automatically.

**Schema changes:** edit the models, then run `alembic revision --autogenerate -m "..."` in `backend/` against a dev database, review the file in `migrations/versions/`, and commit it.

**Existing dev database:** it was created by `create_all`, so mark it as already migrated once: `alembic stamp head`.

**Backups:** schedule `docker compose -f docker-compose.prod.yml exec db pg_dump -U aura aura > backup.sql`, and turn on versioning for the storage bucket.

## 2. Android app

1. **Upload key (once).** Keep this file and its passwords safe; Play needs the same key for every update.
   ```bash
   keytool -genkey -v -keystore ~/aura-upload.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload
   ```
   Create `mobile/android/key.properties` (git-ignored):
   ```
   storePassword=...
   keyPassword=...
   keyAlias=upload
   storeFile=C:/Users/you/aura-upload.jks
   ```
2. **Version.** Bump `version:` in `mobile/pubspec.yaml` (e.g. `1.0.1+2`) and `appVersion` in `lib/core/widgets/settings_sheet.dart`.
3. **Build for Google Play** (the API address must be HTTPS; release builds block plain HTTP):
   ```bash
   cd mobile
   flutter build appbundle --release --dart-define=API_BASE_URL=https://api.example.com/api/v1
   ```
   The output is `build/app/outputs/bundle/release/app-release.aab`. For a sideloadable APK, use `flutter build apk --release ...` instead.
4. **Store listing.**
   - The 512×512 icon is `mobile/tool/play_store_icon_512.png`. Regenerate all icons with `python tool/make_icons.py`.
   - Add screenshots of the Wardrobe, Outfits and Stylist tabs in light and dark mode.

## Local development (unchanged)

```bash
docker compose up -d db redis                                   # repo root
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
cd backend && python -m app.workers.arq_worker
cd mobile && flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000/api/v1   # with `adb reverse tcp:8000 tcp:8000`
```

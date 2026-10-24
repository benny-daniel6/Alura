#!/bin/sh
# Production API entrypoint: apply database migrations, then serve.
set -e
alembic upgrade head
exec uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 \
    --workers "${WEB_CONCURRENCY:-2}" \
    --proxy-headers --forwarded-allow-ips "*"

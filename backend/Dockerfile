FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/aura \
    U2NET_HOME=/home/aura/.u2net

RUN apt-get update && apt-get install -y --no-install-recommends curl libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 aura

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

USER aura

# Bake the ML models into the image so the first upload after a deploy is not slow
RUN python -c "import rembg; rembg.new_session('u2net')" \
    && python -c "import open_clip; open_clip.create_model_and_transforms('ViT-B-32-quickgelu', pretrained='openai')"

COPY --chown=aura:aura . .

# /app is created by root (WORKDIR); give the app user a writable dir for development-mode local storage
USER root
RUN mkdir -p /app/data/storage && chown aura:aura /app /app/data /app/data/storage
USER aura

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# API by default; the worker service overrides the command (see docker-compose.prod.yml)
CMD ["sh", "scripts/start-api.sh"]

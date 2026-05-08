# ============================================================================
# CureFound -- Hugging Face Spaces Dockerfile
# Wrapper that adjusts paths for the monorepo layout (code is in curefound/).
# ============================================================================

# --------------------------------------------------------------------------
# Stage 1: Vite frontend
# --------------------------------------------------------------------------
FROM node:20-alpine AS node-builder
WORKDIR /web

COPY curefound/frontend/package.json curefound/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY curefound/frontend/ ./
RUN npm run build

# --------------------------------------------------------------------------
# Stage 2: Python deps
# --------------------------------------------------------------------------
FROM python:3.11-slim AS py-builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc g++ \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY curefound/pyproject.toml ./

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir \
      --target /build/site-packages \
      "fastapi>=0.115" \
      "uvicorn[standard]>=0.32" \
      "pydantic>=2.7" \
      "pydantic-settings>=2.5" \
      "numpy>=1.26,<2.3" \
      "networkx>=3.2" \
      "structlog>=24" \
      "asgi-correlation-id>=4" \
      "httpx>=0.27"

# --------------------------------------------------------------------------
# Stage 3: runtime
# --------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

RUN groupadd --gid 1001 appgroup \
 && useradd  --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

COPY --from=py-builder /build/site-packages /usr/local/lib/python3.11/site-packages

COPY curefound/app/ ./app/
COPY curefound/data/seed/      ./data/seed/
COPY curefound/data/artifacts/ ./data/artifacts/
COPY --from=node-builder /web/dist ./frontend/dist/
COPY curefound/.env.example ./

ENV ENVIRONMENT=production \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KG_BACKEND=networkx \
    SEED_KG_PATH=data/seed/kg.json \
    ARTIFACTS_DIR=data/artifacts \
    HOST=0.0.0.0 \
    PORT=7860

RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 7860

CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-7860}"]

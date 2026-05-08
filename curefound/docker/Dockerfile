# ============================================================================
# CureFound -- production Dockerfile (single-container, Fly.io ready)
#
# Three stages:
#   1. node-builder  — npm install + Vite production build of the React app.
#   2. py-builder    — pip-install runtime Python deps into a target dir.
#   3. runtime       — slim Python image; copies app code, frontend dist,
#                      installed packages, and the pre-trained model artifacts.
#
# Build:
#   docker build -t curefound -f docker/Dockerfile .
#
# Run locally:
#   docker run --rm -p 8000:8000 \
#     -e ENVIRONMENT=production \
#     curefound
#
# Fly deploy is wired via fly.toml at the repo root.
# ============================================================================

# --------------------------------------------------------------------------
# Stage 1: Vite frontend
# --------------------------------------------------------------------------
FROM node:20-alpine AS node-builder
WORKDIR /web

# Copy lockfile + manifest first so the npm-install layer caches across
# code-only rebuilds.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

# Copy the rest of the frontend tree and build.
# vite.config.ts has `base: "/ui/"` already so asset URLs resolve under /ui.
COPY frontend/ ./
RUN npm run build

# --------------------------------------------------------------------------
# Stage 2: Python deps
# --------------------------------------------------------------------------
FROM python:3.11-slim AS py-builder

# Build deps for any C-extension packages (numpy, etc.).
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc g++ \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./

# Install runtime dependencies into an isolated prefix that we copy into
# the final image. PyTorch is INTENTIONALLY EXCLUDED from the runtime image:
# inference (RotatE scoring) is pure NumPy on the saved complex64 weights.
# torch is only needed for training (`python -m app.ml.rotate` and eval.py)
# which runs offline on the dev machine, not in production.
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

# Non-root user.
RUN groupadd --gid 1001 appgroup \
 && useradd  --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy installed Python packages from the py-builder stage.
COPY --from=py-builder /build/site-packages /usr/local/lib/python3.11/site-packages

# Copy backend application code.
COPY app/ ./app/

# Copy seed KG + pre-trained model artifacts. Raw data is NOT copied
# (large + license-restricted) — repo's .dockerignore excludes data/raw/.
COPY data/seed/      ./data/seed/
COPY data/artifacts/ ./data/artifacts/

# Copy the built frontend bundle from the node-builder stage.
# FastAPI mounts this at /ui/ and serves /ui/index.html for the root path.
COPY --from=node-builder /web/dist ./frontend/dist/

# .env.example documents settings; runtime .env comes from environment
# variables injected by Fly secrets / docker run -e.
COPY .env.example ./

# Tell pydantic-settings not to look for a .env file inside the container —
# all config arrives via environment variables in production.
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

# Make /app writable by the non-root user (logs, etc.).
RUN chown -R appuser:appgroup /app
USER appuser

# 7860 = Hugging Face Spaces default port (also works on Fly.io / local).
EXPOSE 7860

# Shell-form CMD so $PORT expands at runtime (HF Spaces, Fly.io, docker run).
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-7860}"]

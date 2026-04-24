"""FastAPI app factory + module-level `app` instance.

Pattern cribbed from `fastapi/full-stack-fastapi-template`'s `main.py`:
a single top-level `app` is exposed for uvicorn (`uvicorn app.main:app`),
built by a `create_app()` factory that tests can call with an override
Settings instance.

What happens here:
  1. Load (or accept) Settings.
  2. Configure structlog + stdlib logging.
  3. Build the FastAPI instance with title/openapi wiring.
  4. Register CORS middleware + correlation-id middleware.
  5. Register exception handlers.
  6. Mount per-domain routers -- once under /api/v1 for new clients,
     also at the bare path (/repurpose, /health, ...) for backward
     compatibility with the hardened-MVP frontend + tests.
  7. Mount static frontend.
  8. Attach lifespan context manager so startup/shutdown is ordered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

from app.admin.router import router as admin_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.lifespan import lifespan
from app.core.logging import configure_logging, get_logger
from app.core.paths import FRONTEND_DIR, FRONTEND_INDEX
from app.diagnose.router import router as diagnose_router
from app.kg.router import router as kg_router
from app.repurpose.router import router as repurpose_router

if TYPE_CHECKING:
    pass

_log = get_logger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    """OpenAPI `operationId` = "<tag>-<name>". Matches full-stack-fastapi-
    template's generator; yields clean auto-generated client methods like
    `repurposeClient.repurpose_repurpose(...)` instead of the ugly
    default `repurpose_repurpose_post`.
    """
    tag = route.tags[0] if route.tags else "root"
    return f"{tag}-{route.name}"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a FastAPI application. Pass `settings` to override the
    env-backed defaults (used by tests)."""
    settings = settings or get_settings()
    configure_logging(level=settings.LOG_LEVEL, environment=settings.ENVIRONMENT)

    _log.info(
        "create_app.start",
        environment=settings.ENVIRONMENT,
        kg_backend=settings.KG_BACKEND,
        disease_scope=settings.DISEASE_SCOPE,
        project_name=settings.PROJECT_NAME,
    )

    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=(
            "Biomedical KG inference for drug repurposing "
            "(LSD-focused) and rare-disease diagnosis. FYP prototype."
        ),
        version="0.3.0.dev0",
        openapi_url=settings.openapi_url,  # None outside local -> hides /docs too
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        generate_unique_id_function=custom_generate_unique_id,
        lifespan=lifespan,
    )

    # Settings is stashed on app.state so the lifespan (which runs *after*
    # `app` is constructed) can read the override rather than the cached
    # `get_settings()` global. Tests that call `create_app(settings=...)`
    # rely on this.
    app.state.settings = settings

    # ---- Middleware. Correlation-id FIRST so the request-id is available
    # to CORS preflight logs and any later middleware.
    app.add_middleware(CorrelationIdMiddleware, header_name="X-Request-ID")

    if settings.all_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.all_cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )

    # ---- Exception handlers.
    register_exception_handlers(app)

    # ---- Routers. Each domain router ships with its own tag, so the
    # unique-id generator produces `repurpose-repurpose`, `diagnose-
    # diagnose`, etc.
    #
    # We mount each router TWICE -- once under /api/v1 (the new canonical
    # prefix) and once at the bare path (legacy compat with the MVP
    # frontend and the 23 regression tests that hit /repurpose, /diagnose,
    # /subgraph, ... without a version prefix). When the frontend is
    # ported to React in Phase 6, the bare mount can be retired.
    for r in (admin_router, kg_router, repurpose_router, diagnose_router):
        app.include_router(r, prefix=settings.API_V1_STR)
        app.include_router(r)

    # ---- Static frontend.
    if FRONTEND_DIR.exists():
        app.mount(
            "/ui",
            StaticFiles(directory=str(FRONTEND_DIR), html=True),
            name="ui",
        )

    @app.get("/", include_in_schema=False)
    def index():
        if FRONTEND_INDEX.exists():
            return FileResponse(str(FRONTEND_INDEX))
        return {
            "message": (
                "CureFound API is up. See /docs for OpenAPI. "
                "Frontend missing -- build it in /frontend/."
            )
        }

    _log.info("create_app.ready")
    return app


# Module-level app so `uvicorn app.main:app` works without a factory call.
# Lifespan runs when uvicorn (or TestClient) starts the ASGI application.
app = create_app()

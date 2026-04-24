"""Admin / ops endpoints.

Currently just /health. Phase 1 expands this with /admin/ingest/status,
/admin/reload, and anything else reviewers or the FYP panel want as a
health-check lever.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.admin.schemas import HealthResponse
from app.kg.deps import KGDep

router = APIRouter(tags=["admin"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness + KG version",
)
def health(request: Request, kg: KGDep) -> HealthResponse:
    # `kg_backend_name` is populated by lifespan (app.core.lifespan).
    # Defaulting to "networkx" keeps a minimal test fixture that bypasses
    # lifespan still functional.
    backend = getattr(request.app.state, "kg_backend_name", "networkx")
    return HealthResponse(
        status="ok",
        kg_version=kg.version,
        kg_backend=backend,
    )

"""FastAPI lifespan: load KG + RotatE artefacts + services on startup.

Replaces the legacy `_get_state()` module-singleton in `api/main.py`. The
lifespan runs exactly once per app instance — on startup it populates
`app.state` with everything the per-domain `deps.py` factories expect.

Why lifespan and not module-level globals:
  * Testable: `create_app(settings_override=...)` produces a distinct
    FastAPI instance with its own lifespan; tests can spin up isolated
    apps with tiny fixture KGs.
  * Honest about startup cost: reviewers see "KG loading..." in the
    console at boot, not on the first request.

The Neo4j backend was removed during the cleanup pass — we ship a single
NetworkX-backed graph, since the deployed KG is small enough (~700 nodes)
to live entirely in process memory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from app.core.config import Settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI


_log = get_logger(__name__)


def _load_networkx_backend(settings: Settings) -> Any:
    """Load the in-process NetworkX-backed KG and the RotatE artefacts."""
    # Local imports keep `python -c 'import app'` cheap (matters for CLI).
    from app.kg.loader import load_kg
    from app.ml import rotate as kge_mod

    _log.info("lifespan.load.start", backend="networkx", seed_kg=str(settings.seed_kg_path))
    kg = load_kg(settings.seed_kg_path)
    _log.info(
        "lifespan.kg.loaded",
        version=kg.version,
        n_entities=len(kg.idx_to_entity),
        n_relations=len(kg.idx_to_relation),
        n_triples=len(kg.triples),
    )

    # load_for_kg raises ArtifactStaleError if the saved embedding
    # vocabulary no longer matches the current KG.
    E, R, meta = kge_mod.load_for_kg(kg, artifacts_dir=settings.artifacts_dir)
    _log.info(
        "lifespan.kge.loaded",
        model=meta.get("model", "RotatE"),
        dim=int(E.shape[1]) if E.ndim == 2 else None,
        n_entities=int(E.shape[0]) if E.ndim == 2 else None,
        kg_version=meta.get("kg_version"),
    )
    return kg, E, R, meta


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan context. Everything before `yield` runs at startup;
    everything after runs on shutdown."""
    settings: Settings = app.state.settings

    # --------- Startup --------- #
    kg, E, R, meta = _load_networkx_backend(settings)

    # Instantiate service layer. Kept here -- not in deps.py -- so services
    # are built once per app instance, not per request.
    from app.diagnose.service import DiagnoseService
    from app.repurpose.service import RepurposeService, _try_load_distmult_model

    # Optionally load R-GCN / CompGCN artifacts produced by the Colab
    # notebook. They share the lifespan staleness contract: if the .npz
    # file exists but its vocab digest doesn't match the current KG, we
    # let the ArtifactStaleError propagate so the failure is loud.
    extra_models: dict[str, Any] = {}
    for model_name in ("rgcn", "compgcn"):
        head = _try_load_distmult_model(model_name, kg)
        if head is not None:
            extra_models[model_name] = head
            _log.info(
                "lifespan.kge.extra_loaded",
                model=model_name,
                n_entities=int(head.E.shape[0]),
                dim=int(head.E.shape[1]),
            )

    repurpose_service = RepurposeService(kg, E, R, extra_models=extra_models)
    diagnose_service = DiagnoseService(kg)

    app.state.kg = kg
    app.state.kge_E = E
    app.state.kge_R = R
    app.state.kge_meta = meta
    app.state.repurpose_service = repurpose_service
    app.state.diagnose_service = diagnose_service
    app.state.kg_backend_name = "networkx"

    _log.info(
        "lifespan.ready",
        backend="networkx",
        kg_version=kg.version,
        n_drugs=len(getattr(kg, "drugs", []) or []),
        n_diseases=len(getattr(kg, "diseases", []) or []),
        n_symptoms=len(getattr(kg, "symptoms", []) or []),
    )

    try:
        yield
    finally:
        _log.info("lifespan.shutdown", backend="networkx")

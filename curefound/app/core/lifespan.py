"""FastAPI lifespan: load KG + TransE + services on startup; release on shutdown.

Replaces the legacy `_get_state()` module-singleton in `api/main.py`. The
lifespan runs exactly once per app instance -- on startup it populates
`app.state` with everything the per-domain `deps.py` factories expect;
on shutdown it closes the Neo4j driver (Phase 1+) and logs an ingest
summary if one was prepared during a recent ingest task.

Why lifespan and not module-level globals:
  * Testable: `create_app(settings_override=...)` produces a distinct
    FastAPI instance with its own lifespan; tests can spin up isolated
    apps with tiny fixture KGs.
  * Honest about startup cost: reviewers see "KG loading..." in the
    console at boot, not on the first request.
  * Correct shutdown: the Neo4j driver needs an explicit `.close()` to
    flush its bolt connection pool.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from app.core.config import Settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI


_log = get_logger(__name__)


def _load_networkx_backend(settings: Settings) -> Any:
    """Bootstraps the in-process NetworkX-backed KG and TransE artefacts.

    Returns the wrapped `NetworkXBackend` (to be introduced in Phase 1 Step
    5.2). For the refactor we return the raw `KG` dataclass instance --
    the protocol mirrors `KG`'s existing accessors 1:1, so services written
    against `KG` keep working without change once the protocol lands.
    """
    # Local imports: keep startup lazy so `python -c 'import app'` stays
    # cheap (matters for the CLI entrypoints).
    from app.kg.loader import load_kg
    from app.ml import transe as transe_mod

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
    # vocabulary no longer matches the current KG (fix for H4).
    E, R, meta = transe_mod.load_for_kg(kg, artifacts_dir=settings.artifacts_dir)
    _log.info(
        "lifespan.transe.loaded",
        dim=int(E.shape[1]) if E.ndim == 2 else None,
        n_entities=int(E.shape[0]) if E.ndim == 2 else None,
        kg_version=meta.get("kg_version"),
    )
    return kg, E, R, meta


def _load_neo4j_backend(settings: Settings) -> Any:
    """Bootstrap the Neo4j backend + TransE artefacts.

    Requires:
    - A running Neo4j 5 instance at settings.NEO4J_URI
    - KG data already ingested (run python -m app.etl.ingest.all first)
    - TransE artefacts in settings.artifacts_dir (run python run.py train)
    """
    from app.kg.neo4j_backend import Neo4jBackend
    from app.ml import transe as transe_mod

    _log.info(
        "lifespan.load.start",
        backend="neo4j",
        uri=settings.NEO4J_URI,
        db=settings.NEO4J_DATABASE,
    )
    kg = Neo4jBackend(
        uri=settings.NEO4J_URI,
        user=settings.NEO4J_USER,
        password=settings.NEO4J_PASSWORD,
        database=settings.NEO4J_DATABASE,
    )
    _log.info(
        "lifespan.kg.loaded",
        version=kg.version,
        n_entities=len(kg.idx_to_entity),
        n_relations=len(kg.idx_to_relation),
        n_triples=len(kg.triples),
    )

    E, R, meta = transe_mod.load_for_kg(kg, artifacts_dir=settings.artifacts_dir)
    _log.info(
        "lifespan.transe.loaded",
        dim=int(E.shape[1]) if E.ndim == 2 else None,
        n_entities=int(E.shape[0]) if E.ndim == 2 else None,
        kg_version=meta.get("kg_version"),
    )
    return kg, E, R, meta


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan context. Everything before `yield` runs at startup;
    everything after runs on shutdown.
    """
    # Settings is attached by `create_app()` so that tests can inject an
    # override instance without touching the module-level cache.
    settings: Settings = app.state.settings

    # --------- Startup --------- #
    if settings.KG_BACKEND == "networkx":
        kg, E, R, meta = _load_networkx_backend(settings)
    elif settings.KG_BACKEND == "neo4j":
        kg, E, R, meta = _load_neo4j_backend(settings)
    else:  # pragma: no cover -- Settings already type-narrows to Literal
        raise ValueError(f"Unknown KG_BACKEND: {settings.KG_BACKEND!r}")

    # Instantiate service layer. Kept here -- not in deps.py -- so services
    # are built once per app instance, not per request.
    from app.diagnose.service import DiagnoseService
    from app.repurpose.service import RepurposeService

    repurpose_service = RepurposeService(kg, E, R)
    diagnose_service = DiagnoseService(kg)

    app.state.kg = kg
    app.state.transe_E = E
    app.state.transe_R = R
    app.state.transe_meta = meta
    app.state.repurpose_service = repurpose_service
    app.state.diagnose_service = diagnose_service
    app.state.kg_backend_name = settings.KG_BACKEND

    _log.info(
        "lifespan.ready",
        backend=settings.KG_BACKEND,
        kg_version=kg.version,
        n_drugs=len(getattr(kg, "drugs", []) or []),
        n_diseases=len(getattr(kg, "diseases", []) or []),
        n_symptoms=len(getattr(kg, "symptoms", []) or []),
    )

    try:
        yield
    finally:
        # --------- Shutdown --------- #
        # Close the Neo4j driver connection pool if we used the Neo4j backend.
        if settings.KG_BACKEND == "neo4j":
            backend = getattr(app.state, "kg", None)
            close_fn = getattr(backend, "close", None)
            if close_fn is not None:
                with contextlib.suppress(Exception):
                    close_fn()
        _log.info("lifespan.shutdown", backend=settings.KG_BACKEND)

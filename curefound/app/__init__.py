"""CureFound application package.

Layout (zhanymkanov / full-stack-fastapi-template hybrid):

    app/core/               -- cross-cutting infra (config, logging, exceptions,
                               lifespan, paths). No domain logic.
    app/kg/                 -- knowledge graph domain: loader, backend protocol,
                               schemas, service, router, deps, exceptions.
    app/repurpose/          -- drug-repurposing domain.
    app/diagnose/           -- symptom-based diagnosis domain.
    app/admin/              -- health, ingest status, reload triggers.
    app/ml/                 -- TransE training / eval artefacts; technical,
                               consumed by domain services via deps.
    app/etl/                -- seed-KG builder + Phase 1 ingestors.

See README.md and PHASE1_SETUP.md for the full architecture and Phase 1
ingest plan.
"""

from __future__ import annotations

__version__ = "0.3.0.dev0"

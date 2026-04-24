"""Repurpose-domain exception subclasses.

Kept thin -- most routes prefer raising HTTPException(...) directly for
API-surface errors. These live here for service-layer callers that want
typed errors without a FastAPI dependency."""

from __future__ import annotations

from app.core.exceptions import AppError, InvalidInput, NodeNotFound


class DiseaseNotFound(NodeNotFound):
    code = "disease_not_found"


class NotADisease(InvalidInput):
    code = "not_a_disease"


class NoCandidates(AppError):
    code = "no_repurpose_candidates"


__all__ = ["DiseaseNotFound", "NoCandidates", "NotADisease"]

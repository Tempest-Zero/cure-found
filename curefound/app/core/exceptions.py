"""Application-level exception hierarchy + FastAPI handlers.

Rationale (zhanymkanov "don't scatter HTTPException calls in routes"):
routes raise typed domain errors; `register_exception_handlers` maps
each to a consistent JSON envelope `{error, message, details}`. Keeps
the wire format stable and the routes clean.

Domain-specific subclasses live in per-domain `exceptions.py` modules
and inherit from `AppError` here. The handler matches on the base class
so new subclasses work without updating the handler list.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

_log = get_logger(__name__)


class AppError(Exception):
    """Base class for all CureFound-domain errors.

    Subclasses set `code` (short machine-readable string) and optionally
    `http_status`. Callers pass a human-readable message + an optional
    `details` dict that's surfaced verbatim in the response envelope.
    """

    code: str = "app_error"
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


# ---- KG-layer errors (also re-exported from app.kg.exceptions) ------ #


class KGNotLoadedError(AppError):
    code = "kg_not_loaded"
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE


class ArtifactStaleError(AppError):
    """The TransE .npz on disk was trained against a different KG
    vocabulary than the one currently loaded. Matches the legacy
    `ml.transe.ArtifactStaleError` contract; the typed error stays
    defined there and this alias is for handler matching."""

    code = "artifact_stale"
    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR


class NodeNotFound(AppError):
    code = "node_not_found"
    http_status = status.HTTP_404_NOT_FOUND


class InvalidInput(AppError):
    code = "invalid_input"
    http_status = status.HTTP_400_BAD_REQUEST


# ---- Per-domain shortcuts. Full taxonomy lives in <domain>/exceptions.py
# but the handler keys off `AppError`, so those subclasses inherit the
# same envelope automatically.


# ------------------------- handlers ------------------------- #


async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    _log.info(
        "app_error",
        code=exc.code,
        http_status=exc.http_status,
        message=exc.message,
        details=exc.details,
    )
    return JSONResponse(status_code=exc.http_status, content=exc.to_payload())


async def _http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Unify FastAPI's HTTPException output with our AppError envelope.

    The hardened MVP uses `HTTPException(..., detail="...")` in a few
    places (kept during the refactor for test stability); wrap the
    string detail so clients see `{error, message, details}` always.
    """
    payload: dict[str, Any]
    if isinstance(exc.detail, dict):
        # Wrap dict details in FastAPI's standard `{"detail": {...}}` envelope
        # so regression tests that do `r.json()["detail"]["key"]` keep passing.
        # This matches the shape FastAPI's own default HTTPException handler
        # returns; our handler only customises the string-detail path.
        payload = {"detail": exc.detail}
    else:
        payload = {
            "error": f"http_{exc.status_code}",
            "message": str(exc.detail),
            "details": {},
        }
    return JSONResponse(status_code=exc.status_code, content=payload)


async def _validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 from Pydantic validation. Preserves the raw `detail` list so
    the FastAPI-standard validation-error payload stays parseable by the
    UI (the hardened tests assert on `r.status_code == 422` only, so the
    body shape is flexible). We keep `detail` at the top level to stay
    compatible with legacy clients that do `r.json()["detail"]`."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": exc.body},
    )


async def _unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    _log.exception("unhandled_exception", exc_type=type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_error",
            "message": "An internal error occurred.",
            "details": {},
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire the handlers above onto the FastAPI instance.

    Order matters for Starlette: more specific classes registered later
    shadow earlier ones. AppError is registered first so its subclasses
    (from domain `exceptions.py` files) are caught by the base handler
    unless a subclass registers its own.
    """
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    # `Exception` catches anything not covered above -- last line of defence.
    app.add_exception_handler(Exception, _unhandled_exception_handler)

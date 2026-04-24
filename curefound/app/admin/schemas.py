"""Admin-surface schemas."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    kg_version: str
    kg_backend: str


__all__ = ["HealthResponse"]

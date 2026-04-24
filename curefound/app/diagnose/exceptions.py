"""Diagnosis-domain exception subclasses."""

from __future__ import annotations

from app.core.exceptions import InvalidInput


class NoResolvableSymptoms(InvalidInput):
    code = "no_resolvable_symptoms"


__all__ = ["NoResolvableSymptoms"]

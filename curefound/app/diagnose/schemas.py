"""Request/response schemas for the diagnosis endpoint.

Moved from the hardened MVP's `api/main.py`. Field docs are pinned by
README (`Scoring semantics`) and by the regression tests -- do not change
them lightly.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DiagnoseRequest(BaseModel):
    symptoms: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "One or more HPO ids ('HP:0001250') or canonical Symptom ids "
            "('S:SEIZURES'). Case-insensitive. At least one token must be "
            "resolvable; unresolvable tokens are reported in "
            "`unresolved_inputs` rather than silently dropped."
        ),
    )
    top_k: int = Field(10, ge=1, le=50)


class SymptomBrief(BaseModel):
    id: str
    name: str
    hpo_id: str | None = None


class DiagnoseCandidate(BaseModel):
    disease_id: str
    disease_name: str
    jaccard_score: float = Field(
        ...,
        description="|overlap| / |union| between input and disease symptoms.",
    )
    idf_score: float = Field(
        ...,
        description=(
            "Sum of smoothed-IDF weights of overlapping symptoms. "
            "idf(s) = log((1+N)/(1+df(s))) + 1, so rare symptoms count more."
        ),
    )
    fused_score: float = Field(
        ...,
        description="Reciprocal Rank Fusion of Jaccard and IDF rankings, k=60.",
    )
    matched_symptoms: list[SymptomBrief]
    missing_symptoms: list[SymptomBrief]
    is_rare: bool


class DiagnoseResponse(BaseModel):
    resolved_inputs: list[str] = Field(
        ...,
        description=(
            "Canonical Symptom ids the server was able to map from the raw "
            "input. Always a subset of the request."
        ),
    )
    unresolved_inputs: list[str] = Field(
        default_factory=list,
        description=(
            "Input tokens that could not be mapped to any KG Symptom. The UI "
            "should flag these so the user knows why no result covers them."
        ),
    )
    candidates: list[DiagnoseCandidate]


__all__ = [
    "DiagnoseCandidate",
    "DiagnoseRequest",
    "DiagnoseResponse",
    "SymptomBrief",
]

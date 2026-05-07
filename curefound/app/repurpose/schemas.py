"""Request/response schemas for the drug-repurposing endpoint.

Moved verbatim from the hardened MVP's `api/main.py` -- the wire format
and field docs are pinned by the README's `Scoring semantics` section and
by the regression tests. Keep field docstrings current; they render as
the OpenAPI description.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Canonical Disease node id (D:NPC) or external id (MONDO/OMIM/ORPHA). Accepts
# upper+lowercase; /repurpose's resolver is case-insensitive.
DISEASE_INPUT_RE = (
    r"^(?:D:[A-Za-z0-9_]+|MONDO:\d{7}|mondo:\d{7}"
    r"|OMIM:\d{6}|omim:\d{6}"
    r"|ORPHA:\d+|orpha:\d+)$"
)


class RepurposeRequest(BaseModel):
    disease_id: str = Field(
        ...,
        description=(
            "Canonical Disease node id (D:NPC) or external id "
            "(MONDO:0009937, OMIM:257220, ORPHA:646). Case-insensitive."
        ),
        pattern=DISEASE_INPUT_RE,
    )
    top_k: int = Field(10, ge=1, le=50)
    include_already_approved: bool = Field(
        False,
        description=(
            "If true, approved TREATS edges are included in the candidate "
            "set. If false (default), approved drugs are excluded BEFORE "
            "ranking so model_rank / graph_rank describe the "
            "novel-prediction universe."
        ),
    )


class EvidenceEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(..., alias="from")
    to: str
    rel: str
    direction: str | None = Field(
        None,
        description=(
            "'forward' if the KG edge runs from->to, 'reverse' if we "
            "traversed it backwards. Lets the UI visually distinguish "
            "inferred reverse traversals from directly-stored evidence."
        ),
    )
    approval_year: int | None = None
    action: str | None = None
    provenance: str | None = Field(
        None,
        description="Source DB of the fact ('seed', 'drugcentral', ...).",
    )


class RepurposeCandidate(BaseModel):
    drug_id: str
    drug_name: str
    model_score: float = Field(
        ...,
        description=(
            "RotatE score, -||h o r - t||_2 in complex space (relational rotation, "
            "Sun et al. ICLR 2019). Higher is better; scale is model-dependent and "
            "not comparable across retrains."
        ),
    )
    graph_score: float = Field(
        ...,
        description=(
            "Jaccard overlap of pathway neighborhoods: "
            "|drug.pathways n disease.pathways| / |union|, in [0, 1]."
        ),
    )
    fused_score: float = Field(
        ...,
        description=(
            "Reciprocal Rank Fusion of (model_rank, graph_rank) with k=60. "
            "Higher is better; this is the field used to order the response."
        ),
    )
    model_rank: int = Field(
        ...,
        description=(
            "1-indexed rank by model_score WITHIN the returned candidate set "
            "(approved drugs are excluded when "
            "include_already_approved=False)."
        ),
    )
    graph_rank: int = Field(
        ...,
        description="1-indexed rank by graph_score within the same set.",
    )
    already_approved: bool
    approval_year: int | None
    evidence_paths: list[list[EvidenceEdge]]


class RepurposeResponse(BaseModel):
    disease_id: str
    disease_name: str
    candidates: list[RepurposeCandidate]


__all__ = [
    "DISEASE_INPUT_RE",
    "EvidenceEdge",
    "RepurposeCandidate",
    "RepurposeRequest",
    "RepurposeResponse",
]

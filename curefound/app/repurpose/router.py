"""Drug-repurposing HTTP route: POST /repurpose.

Route stays thin: validates input, resolves external ids, delegates
ranking to `RepurposeService.predict`, marshals the result into the
response envelope. All business logic (RotatE scoring, pathway Jaccard,
RRF fusion, evidence paths) is in the service.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.kg.deps import KGDep
from app.repurpose.deps import RepurposeDep
from app.repurpose.schemas import (
    EvidenceEdge,
    RepurposeCandidate,
    RepurposeRequest,
    RepurposeResponse,
)

router = APIRouter(tags=["repurpose"])


@router.post(
    "/repurpose",
    response_model=RepurposeResponse,
    summary="Rank drug candidates for a disease",
)
def repurpose(
    req: RepurposeRequest,
    kg: KGDep,
    svc: RepurposeDep,
) -> RepurposeResponse:
    # Resolve via the O(1) xref index (hardening fix H2 -- was a linear scan).
    disease_id = req.disease_id
    if disease_id not in kg.node_by_id:
        resolved = kg.resolve_external_id(disease_id)
        if resolved is not None:
            disease_id = resolved
    if disease_id not in kg.node_by_id:
        raise HTTPException(404, f"Unknown disease id: {req.disease_id}")
    if kg.node_by_id[disease_id]["type"] != "Disease":
        raise HTTPException(400, f"{req.disease_id} is not a Disease")

    results = svc.predict(
        disease_id,
        top_k=req.top_k,
        include_already_approved=req.include_already_approved,
    )
    cands = [
        RepurposeCandidate(
            drug_id=r.drug_id,
            drug_name=r.drug_name,
            model_score=r.model_score,
            graph_score=r.graph_score,
            fused_score=r.fused_score,
            model_rank=r.model_rank,
            graph_rank=r.graph_rank,
            already_approved=r.already_approved,
            approval_year=r.approval_year,
            evidence_paths=[
                [
                    EvidenceEdge(
                        **{
                            "from": ed["from"],
                            "to": ed["to"],
                            "rel": ed["rel"],
                            "direction": ed.get("direction"),
                            "approval_year": ed.get("approval_year"),
                            "action": ed.get("action"),
                            "provenance": ed.get("provenance"),
                        }
                    )
                    for ed in p
                ]
                for p in r.evidence_paths
            ],
        )
        for r in results
    ]
    return RepurposeResponse(
        disease_id=disease_id,
        disease_name=kg.node_by_id[disease_id]["name"],
        candidates=cands,
    )

"""Symptom-based diagnosis route: POST /diagnose.

Surfaces unresolved input tokens in the response (hardening fix C3 --
the old endpoint silently dropped them). Route stays thin: service owns
ranking, router marshals.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.diagnose.deps import DiagnoseDep
from app.diagnose.schemas import (
    DiagnoseCandidate,
    DiagnoseRequest,
    DiagnoseResponse,
    SymptomBrief,
)

router = APIRouter(tags=["diagnose"])


@router.post(
    "/diagnose",
    response_model=DiagnoseResponse,
    summary="Rank diseases by symptom overlap",
)
def diagnose(req: DiagnoseRequest, svc: DiagnoseDep) -> DiagnoseResponse:
    # Fix for C3: resolve once here and pass the resolution into predict()
    # so the service does not re-resolve internally. Surface unresolved
    # tokens in the response so the UI can highlight them -- the old
    # endpoint silently dropped them and let the client think nothing had
    # "matched".
    resolved, unresolved = svc.resolve_inputs(req.symptoms)
    if not resolved:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "no_resolvable_symptoms",
                "unresolved": unresolved,
                "message": (
                    "None of the provided symptom ids could be mapped to a "
                    "Symptom node in the KG. Check that they are HPO ids of "
                    "the form HP:NNNNNNN, canonical S:NAME ids, or one of "
                    "the symptoms surfaced by /search."
                ),
            },
        )
    results = svc.predict(req.symptoms, top_k=req.top_k, resolved=resolved)
    cands = [
        DiagnoseCandidate(
            disease_id=r.disease_id,
            disease_name=r.disease_name,
            jaccard_score=r.jaccard_score,
            idf_score=r.idf_score,
            fused_score=r.fused_score,
            matched_symptoms=[SymptomBrief(**m) for m in r.matched_symptoms],
            missing_symptoms=[SymptomBrief(**m) for m in r.missing_symptoms],
            is_rare=r.is_rare,
        )
        for r in results
    ]
    return DiagnoseResponse(
        resolved_inputs=resolved,
        unresolved_inputs=unresolved,
        candidates=cands,
    )

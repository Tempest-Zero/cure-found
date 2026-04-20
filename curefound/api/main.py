"""
CureFound FastAPI app. Endpoints:
  GET  /health
  GET  /stats                                -- KG version + counts
  GET  /search?q=&type=&limit=                -- autocomplete
  GET  /node/{node_id}                        -- node details + xrefs
  GET  /subgraph?node_id=&k=&max_nodes=       -- Cytoscape subgraph around a node
  POST /repurpose    {disease_id, top_k, include_already_approved}
  POST /diagnose     {symptoms: [hpo_ids...], top_k}

Static UI is served from /frontend/.

Input validation and error contracts (see audit plan, sprint fixes
C3 / H4 / H6 / M1 / M2):

  * Pydantic models use `min_length` + regex on canonical / HPO / MONDO /
    OMIM / ORPHA id shapes -- malformed inputs now fail with 422 at the
    validation layer instead of returning 200 + empty results.
  * /diagnose surfaces an `unresolved_inputs` array so the UI can flag
    HPO ids it could not map, instead of silently dropping them.
  * The TransE artifact is loaded via `load_for_kg()`, which raises
    ArtifactStaleError if the saved embedding vocabulary no longer
    matches the seed -- catches "I edited the KG and forgot to retrain".
  * CORS origins are configurable via the CUREFOUND_CORS_ORIGINS env var.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

# Make sibling packages importable when run as `uvicorn api.main:app`
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kg.loader import load_kg                                          # noqa: E402
from ml import transe as transe_mod                                    # noqa: E402
from api.services.repurpose import RepurposeService                    # noqa: E402
from api.services.diagnose import DiagnoseService                      # noqa: E402


# ---------------- Validation patterns ---------------- #

# Canonical node id: TYPE:local (e.g. "D:NPC", "S:SEIZURES"). HPO alias
# HP:NNNNNNN and MONDO/OMIM/ORPHA external ids are accepted on endpoints that
# resolve via kg.resolve_external_id(...).
_DISEASE_INPUT_RE = (
    r"^(?:D:[A-Za-z0-9_]+|MONDO:\d{7}|mondo:\d{7}"
    r"|OMIM:\d{6}|omim:\d{6}"
    r"|ORPHA:\d+|orpha:\d+)$"
)
_NODE_ID_RE = r"^[A-Z]{1,4}:[A-Za-z0-9_]+$"


# ---------------- Request / response models ---------------- #


class HealthResponse(BaseModel):
    status: str
    kg_version: str


class StatsResponse(BaseModel):
    kg_version: str
    n_entities: int
    n_relations: int
    n_triples: int
    by_node_type: dict[str, int]
    by_rel_type: dict[str, int]


class NodeBrief(BaseModel):
    id: str
    name: str
    type: str
    xrefs: dict[str, Any] | None = None


class NodeDetail(NodeBrief):
    is_rare: bool | None = None
    inheritance: str | None = None
    approval_year: int | None = None
    is_approved: bool | None = None
    in_degree: int
    out_degree: int


class RepurposeRequest(BaseModel):
    disease_id: str = Field(
        ...,
        description=(
            "Canonical Disease node id (D:NPC) or external id "
            "(MONDO:0009937, OMIM:257220, ORPHA:646). Case-insensitive."
        ),
        pattern=_DISEASE_INPUT_RE,
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
            "TransE score, -||h + r - t||_2. Higher is better; typical range "
            "[-3, 0] on the seed KG, scale is model-dependent."
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
        ..., description="|overlap| / |union| between input and disease symptoms."
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


class SubgraphNode(BaseModel):
    data: dict[str, Any]


class SubgraphEdge(BaseModel):
    data: dict[str, Any]


class SubgraphResponse(BaseModel):
    nodes: list[SubgraphNode]
    edges: list[SubgraphEdge]


# ---------------- App setup ---------------- #

app = FastAPI(
    title="CureFound API",
    description="Biomedical KG inference for drug repurposing and rare-disease diagnosis (MVP).",
    version="0.1.0-mvp",
)


def _cors_origins() -> list[str]:
    """Read CORS origins from CUREFOUND_CORS_ORIGINS (comma-separated).
    Default: localhost on the usual dev ports. Fix for M2 -- the previous
    blanket `*` is a credential-exfiltration footgun once auth lands."""
    raw = os.environ.get("CUREFOUND_CORS_ORIGINS", "").strip()
    if not raw:
        return [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy global state -- loaded on first request, cached forever.
_state: dict[str, Any] = {}


def _get_state() -> dict[str, Any]:
    if not _state:
        kg = load_kg()
        # load_for_kg raises ArtifactStaleError if the saved embedding
        # vocabulary no longer matches the current KG (fix for H4).
        E, R, meta = transe_mod.load_for_kg(kg)
        _state["kg"] = kg
        _state["E"] = E
        _state["R"] = R
        _state["meta"] = meta
        _state["repurpose"] = RepurposeService(kg, E, R)
        _state["diagnose"] = DiagnoseService(kg)
    return _state


@app.get("/health", response_model=HealthResponse)
def health():
    kg = _get_state()["kg"]
    return HealthResponse(status="ok", kg_version=kg.version)


@app.get("/stats", response_model=StatsResponse)
def stats():
    s = _get_state()
    kg = s["kg"]
    by_node: dict[str, int] = {}
    for n in kg.node_by_id.values():
        by_node[n["type"]] = by_node.get(n["type"], 0) + 1
    by_rel: dict[str, int] = {}
    for e in kg.triples_with_props:
        by_rel[e["rel"]] = by_rel.get(e["rel"], 0) + 1
    return StatsResponse(
        kg_version=kg.version,
        n_entities=len(kg.idx_to_entity),
        n_relations=len(kg.idx_to_relation),
        n_triples=len(kg.triples),
        by_node_type=by_node,
        by_rel_type=by_rel,
    )


@app.get("/search", response_model=list[NodeBrief])
def search(
    q: str = Query(..., min_length=1),
    type: str | None = Query(None, description="Disease | Gene | Protein | Drug | Pathway | Symptom"),
    limit: int = Query(20, ge=1, le=50),
):
    kg = _get_state()["kg"]
    types = [type] if type else None
    results = kg.search(q, types=types, limit=limit)
    return [
        NodeBrief(id=n["id"], name=n["name"], type=n["type"], xrefs=n.get("xrefs"))
        for n in results
    ]


@app.get("/node/{node_id}", response_model=NodeDetail)
def get_node(node_id: str):
    kg = _get_state()["kg"]
    # Accept canonical or external id transparently -- the UI occasionally
    # rehydrates from a user-pasted MONDO/HPO/UniProt id.
    canonical = node_id if node_id in kg.node_by_id else kg.resolve_external_id(node_id)
    if canonical is None:
        raise HTTPException(404, f"Unknown node id: {node_id}")
    n = kg.node(canonical)
    if n is None:
        raise HTTPException(404, f"Unknown node id: {node_id}")
    in_deg = kg.graph.in_degree(canonical) if canonical in kg.graph else 0
    out_deg = kg.graph.out_degree(canonical) if canonical in kg.graph else 0
    return NodeDetail(
        id=n["id"], name=n["name"], type=n["type"], xrefs=n.get("xrefs"),
        is_rare=n.get("is_rare"),
        inheritance=n.get("inheritance"),
        approval_year=n.get("approval_year"),
        is_approved=n.get("is_approved"),
        in_degree=in_deg, out_degree=out_deg,
    )


@app.get("/subgraph", response_model=SubgraphResponse)
def subgraph(
    node_id: str = Query(..., pattern=_NODE_ID_RE),
    k: int = Query(2, ge=1, le=3),
    max_nodes: int = Query(100, ge=10, le=200),
):
    kg = _get_state()["kg"]
    if node_id not in kg.node_by_id:
        raise HTTPException(404, f"Unknown node id: {node_id}")
    sub = kg.subgraph_around(node_id, k=k, max_nodes=max_nodes)
    return SubgraphResponse(
        nodes=[SubgraphNode(data=n["data"]) for n in sub["nodes"]],
        edges=[SubgraphEdge(data=e["data"]) for e in sub["edges"]],
    )


@app.post("/repurpose", response_model=RepurposeResponse)
def repurpose(req: RepurposeRequest):
    s = _get_state()
    kg = s["kg"]
    svc = s["repurpose"]
    # Resolve via the O(1) xref index (fix for H2 -- was a linear scan).
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


@app.post("/diagnose", response_model=DiagnoseResponse)
def diagnose(req: DiagnoseRequest):
    s = _get_state()
    svc = s["diagnose"]
    # Fix for C3: resolve once here and pass the resolution into predict() so
    # it does not re-resolve internally. Surface unresolved tokens in the
    # response so the UI can highlight them -- the old endpoint silently
    # dropped them and let the client think nothing had "matched".
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


# ---------------- Static frontend ---------------- #

FRONTEND_DIR = ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="ui")


@app.get("/")
def index():
    index_html = FRONTEND_DIR / "index.html"
    if index_html.exists():
        return FileResponse(str(index_html))
    return {"message": "CureFound API is up. See /docs for OpenAPI. Frontend missing — build it in /frontend/."}

"""KG-domain HTTP routes: /search, /node/{id}, /subgraph, /stats.

Routes are thin: validate input, call into kg accessors, map to response
schemas. Anything resembling ranking or business logic lives in the
repurpose/diagnose services.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.kg.deps import KGDep
from app.kg.schemas import (
    NODE_ID_RE,
    NodeBrief,
    NodeDetail,
    StatsResponse,
    SubgraphEdge,
    SubgraphNode,
    SubgraphResponse,
)

router = APIRouter(tags=["kg"])


@router.get("/stats", response_model=StatsResponse, summary="KG version + counts")
def stats(kg: KGDep) -> StatsResponse:
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


@router.get("/search", response_model=list[NodeBrief], summary="Substring search")
def search(
    kg: KGDep,
    q: str = Query(..., min_length=1),
    type: str | None = Query(
        None,
        description="Disease | Gene | Protein | Drug | Pathway | Symptom",
    ),
    limit: int = Query(20, ge=1, le=50),
) -> list[NodeBrief]:
    types = [type] if type else None
    results = kg.search(q, types=types, limit=limit)
    return [
        NodeBrief(id=n["id"], name=n["name"], type=n["type"], xrefs=n.get("xrefs")) for n in results
    ]


@router.get("/node/{node_id}", response_model=NodeDetail, summary="Node details")
def get_node(kg: KGDep, node_id: str) -> NodeDetail:
    # Accept canonical or external id transparently (the UI occasionally
    # rehydrates from a user-pasted MONDO/HPO/UniProt id).
    canonical = node_id if node_id in kg.node_by_id else kg.resolve_external_id(node_id)
    if canonical is None:
        raise HTTPException(404, f"Unknown node id: {node_id}")
    n = kg.node(canonical)
    if n is None:
        raise HTTPException(404, f"Unknown node id: {node_id}")
    in_deg = kg.graph.in_degree(canonical) if canonical in kg.graph else 0
    out_deg = kg.graph.out_degree(canonical) if canonical in kg.graph else 0
    return NodeDetail(
        id=n["id"],
        name=n["name"],
        type=n["type"],
        xrefs=n.get("xrefs"),
        is_rare=n.get("is_rare"),
        inheritance=n.get("inheritance"),
        approval_year=n.get("approval_year"),
        is_approved=n.get("is_approved"),
        in_degree=in_deg,
        out_degree=out_deg,
    )


@router.get("/subgraph", response_model=SubgraphResponse, summary="k-hop subgraph")
def subgraph(
    kg: KGDep,
    node_id: str = Query(..., pattern=NODE_ID_RE),
    k: int = Query(2, ge=1, le=3),
    max_nodes: int = Query(100, ge=10, le=200),
) -> SubgraphResponse:
    if node_id not in kg.node_by_id:
        raise HTTPException(404, f"Unknown node id: {node_id}")
    sub = kg.subgraph_around(node_id, k=k, max_nodes=max_nodes)
    return SubgraphResponse(
        nodes=[SubgraphNode(data=n["data"]) for n in sub["nodes"]],
        edges=[SubgraphEdge(data=e["data"]) for e in sub["edges"]],
    )

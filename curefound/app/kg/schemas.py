"""Pydantic request/response schemas for the KG domain.

Covers /search, /node/{id}, /subgraph, /stats. Kept as thin response
envelopes around `kg.loader`'s return types -- services return dicts,
these schemas validate the shape on the way out.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# Canonical node id regex: TYPE:local (e.g. "D:NPC", "S:SEIZURES", "DR:HPBCD").
# HPO alias `HP:NNNNNNN` and MONDO/OMIM/ORPHA external ids are accepted on
# endpoints that resolve via `kg.resolve_external_id(...)`.
NODE_ID_RE = r"^[A-Z]{1,4}:[A-Za-z0-9_]+$"


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


class SubgraphNode(BaseModel):
    data: dict[str, Any]


class SubgraphEdge(BaseModel):
    data: dict[str, Any]


class SubgraphResponse(BaseModel):
    nodes: list[SubgraphNode]
    edges: list[SubgraphEdge]


__all__ = [
    "NODE_ID_RE",
    "HealthResponse",
    "NodeBrief",
    "NodeDetail",
    "StatsResponse",
    "SubgraphEdge",
    "SubgraphNode",
    "SubgraphResponse",
]

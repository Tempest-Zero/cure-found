"""
KG loader. Reads data/seed/kg.json and builds:
  - an in-memory NetworkX MultiDiGraph
  - compact integer entity / relation indexes for ML
  - lookup tables for names, types, xrefs
  - O(1) indexes:  treats_edge  (drug, disease) -> edge dict
                   xref_index   case-normalized external id -> canonical id

This is the single source of truth for "what's in the KG" throughout the app.
In Phase 1 the underlying store swaps to Neo4j and these same accessors stay
the same (see `KG.subgraph_around(...)`, `KG.search(...)`,
`KG.resolve_external_id(...)` -- used by api/services/*).
"""
from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from typing import Any, Iterable

import networkx as nx


DEFAULT_KG_PATH = Path(__file__).resolve().parents[1] / "data" / "seed" / "kg.json"

_LOG = logging.getLogger(__name__)


# Relation labels that may appear in any loaded KG. Extending the seed requires
# adding the new label here so _validate() does not reject it.
KNOWN_RELATIONS = {
    "CAUSES", "ENCODES", "TARGETS", "TREATS",
    "HAS_PHENOTYPE", "PARTICIPATES_IN", "ASSOCIATED_WITH",
}

KNOWN_NODE_TYPES = {"Disease", "Gene", "Protein", "Drug", "Pathway", "Symptom"}


# Semantic weights for evidence-path scoring. Mechanistic chains
# (drug -> TARGETS -> protein -> ENCODED_BY -> gene -> CAUSES -> disease) beat
# phenotype chains of the same length; adjusts for H5 in the audit plan.
_REL_WEIGHT = {
    "TARGETS":         3.0,
    "CAUSES":          3.0,
    "ENCODES":         2.5,
    "TREATS":          2.5,
    "ASSOCIATED_WITH": 2.0,
    "PARTICIPATES_IN": 1.5,
    "HAS_PHENOTYPE":   1.0,
}


# External-id namespaces that KG nodes carry as xrefs. Keys kept in sync with
# etl.id_map_service.SUPPORTED_NAMESPACES.
_XREF_NAMESPACES = {
    "mondo_id", "omim_id", "orpha_id",
    "hgnc_id", "ncbi_gene_id",
    "uniprot_id",
    "drugcentral_id", "chembl_id", "pubchem_cid",
    "reactome_id", "kegg_id",
    "hpo_id",
}


class KGValidationError(ValueError):
    """Raised by _validate() when the seed JSON is internally inconsistent."""


@dataclass
class KG:
    version: str
    graph: nx.MultiDiGraph
    node_by_id: dict[str, dict]
    entity_to_idx: dict[str, int]
    idx_to_entity: list[str]
    relation_to_idx: dict[str, int]
    idx_to_relation: list[str]
    triples: list[tuple[int, int, int]]        # (h_idx, r_idx, t_idx)
    triples_with_props: list[dict]              # original edge dicts
    # Convenience caches
    drugs: list[str] = field(default_factory=list)
    diseases: list[str] = field(default_factory=list)
    symptoms: list[str] = field(default_factory=list)
    # O(1) lookup tables built at load time
    treats_edge: dict[tuple[str, str], dict] = field(default_factory=dict)
    xref_index: dict[str, str] = field(default_factory=dict)

    # -------------------- accessors used by API layer -------------------- #

    def node(self, node_id: str) -> dict | None:
        return self.node_by_id.get(node_id)

    def resolve_external_id(self, ext_id: str) -> str | None:
        """Map an external identifier (MONDO:..., HP:..., HGNC:..., UniProt:...,
        DrugCentral:..., OMIM:..., ORPHA:...) or canonical id to a canonical KG
        node id. Case-insensitive. Returns None on miss.

        Accepts the canonical id itself too, so a caller that has already
        canonicalized does not need a special-case path.
        """
        if not ext_id or not isinstance(ext_id, str):
            return None
        return self.xref_index.get(ext_id.strip().upper())

    def search(self, query: str, types: Iterable[str] | None = None, limit: int = 20) -> list[dict]:
        """Substring search on node name (case-insensitive). Ties broken by
        canonical id (alphabetical) so output is reproducible across runs and
        python versions (H7 in the audit plan)."""
        q = query.strip().lower()
        if not q:
            return []
        types_set = set(types) if types else None
        out: list[tuple[tuple[int, int, str], dict]] = []
        for n in self.node_by_id.values():
            if types_set and n["type"] not in types_set:
                continue
            name = n["name"].lower()
            if q not in name:
                continue
            # Score: exact match > prefix > substring. Shorter name wins ties.
            # Canonical id tiebreaks so results are deterministic.
            if name == q:
                score = 0
            elif name.startswith(q):
                score = 1
            else:
                score = 2
            out.append(((score, len(name), n["id"]), n))
        out.sort(key=lambda x: x[0])
        return [n for _, n in out[:limit]]

    def subgraph_around(self, node_id: str, k: int = 2, max_nodes: int = 200) -> dict:
        """Deterministic BFS up to `k` hops from `node_id`. Returns a Cytoscape
        friendly `{nodes, edges}` dict.

        Guarantees (addresses C2 and C5 in the audit plan):
          1. The seed `node_id` is always present in `nodes`.
          2. Enqueue order is alphabetical on neighbor ids, so the response is
             byte-identical across processes regardless of PYTHONHASHSEED.
          3. The BFS stops enqueueing as soon as `len(visited) == max_nodes`;
             no post-hoc set slicing.
          4. Every emitted edge has both endpoints in `visited`, and the
             `source`/`target` keys carry canonical node ids -- Cytoscape can
             render them.
          5. The edge provenance (which DB this fact came from) is surfaced as
             `provenance`, NOT `source`, so it never clobbers Cytoscape's
             structural `data.source`.
        """
        if node_id not in self.graph or node_id not in self.node_by_id:
            return {"nodes": [], "edges": []}

        visited: set[str] = {node_id}
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])

        while queue and len(visited) < max_nodes:
            cur, dist = queue.popleft()
            if dist >= k:
                continue
            # Alphabetical neighbor order -> reproducible frontier.
            neighbors = sorted(
                set(self.graph.successors(cur)) | set(self.graph.predecessors(cur))
            )
            for nb in neighbors:
                if nb in visited or nb not in self.node_by_id:
                    continue
                if len(visited) >= max_nodes:
                    break
                visited.add(nb)
                queue.append((nb, dist + 1))

        # Emit nodes in sorted order so JSON digests are stable.
        nodes = [
            {
                "data": {
                    "id": nid,
                    "label": self.node_by_id[nid]["name"],
                    "type": self.node_by_id[nid]["type"],
                }
            }
            for nid in sorted(visited)
        ]

        edges: list[dict] = []
        for u, v, key, data in self.graph.edges(keys=True, data=True):
            if u not in visited or v not in visited:
                continue
            payload: dict[str, Any] = {
                "id": f"{u}__{data['rel']}__{v}__{key}",
                "source": u,                 # Cytoscape source-node id
                "target": v,                 # Cytoscape target-node id
                "label": data["rel"],
            }
            # Copy optional attrs, renaming the provenance field from "source"
            # to "provenance" so it never overwrites the structural "source"
            # above. Fix for C5.
            for src_key, dst_key in (
                ("approval_year", "approval_year"),
                ("action",        "action"),
                ("frequency",     "frequency"),
                ("source",        "provenance"),
            ):
                if src_key in data and data[src_key] is not None:
                    payload[dst_key] = data[src_key]
            edges.append({"data": payload})

        edges.sort(
            key=lambda e: (
                e["data"]["source"],
                e["data"]["target"],
                e["data"]["label"],
                e["data"]["id"],
            )
        )
        return {"nodes": nodes, "edges": edges}

    def evidence_paths(
        self, head: str, tail: str, k: int = 3, max_paths: int = 10,
    ) -> list[list[dict]]:
        """Find up to `max_paths` semantically-ranked simple paths head->tail
        of length <= k. Each returned path is a list of edge dicts:

          from, to      canonical node ids. `from`/`to` always follow the
                        traversal direction so consumers can render the full
                        node sequence even when an edge was taken in reverse
                        (addresses H5 in the audit plan; previously the
                        reversed-edge display elided the intermediate node).
          rel           relation label
          direction     "forward" if the KG edge runs head->tail along this
                        hop, "reverse" if we traversed it the other way
          approval_year, action, provenance   optional metadata copied from
                        the edge (provenance was "source" in the raw data)

        Scoring: semantic_score = sum(_REL_WEIGHT[rel]). Paths sorted by
        (-score, length, sequence_hash) so mechanistic chains (TARGETS-ENCODES-
        CAUSES) outrank long HAS_PHENOTYPE chains of the same length. Dedup
        is on the full node sequence, so parallel routes through different
        Gaucher-treating drugs collapse -- no more "four identical-looking
        chains" as in the current display bug.

        Enumeration is capped at 100 candidate simple paths (bounds cost for
        Phase-1 denser graphs; the seed KG never hits this cap).
        """
        if head not in self.graph or tail not in self.graph or head == tail:
            return []
        try:
            undirected = self.graph.to_undirected(as_view=True)
            node_paths = list(
                islice(
                    nx.all_simple_paths(undirected, head, tail, cutoff=k),
                    100,
                )
            )
        except nx.NodeNotFound:
            return []

        scored: list[tuple[float, int, str, list[dict]]] = []
        seen_sequences: set[tuple[str, ...]] = set()
        for node_seq in node_paths:
            seq = tuple(node_seq)
            if seq in seen_sequences:
                continue
            seen_sequences.add(seq)

            edge_path: list[dict] = []
            score = 0.0
            ok = True
            for a, b in zip(node_seq, node_seq[1:]):
                fwd = list(self.graph.get_edge_data(a, b, default={}).values())
                rev = list(self.graph.get_edge_data(b, a, default={}).values())
                # Prefer forward edge; among parallel edges, pick the
                # highest-semantic-weight relation for stable display.
                if fwd:
                    d = max(fwd, key=lambda e: _REL_WEIGHT.get(e.get("rel"), 0.0))
                    direction = "forward"
                elif rev:
                    d = max(rev, key=lambda e: _REL_WEIGHT.get(e.get("rel"), 0.0))
                    direction = "reverse"
                else:
                    _LOG.info("evidence_paths: missing edge data %s<->%s", a, b)
                    ok = False
                    break
                rel = d.get("rel")
                if rel is None:
                    ok = False
                    break
                score += _REL_WEIGHT.get(rel, 0.5)
                edge: dict[str, Any] = {
                    "from": a,                 # traversal direction:
                    "to": b,                   # always the NEXT node in node_seq
                    "rel": rel,
                    "direction": direction,
                }
                for src_key, dst_key in (
                    ("approval_year", "approval_year"),
                    ("action",        "action"),
                    ("source",        "provenance"),
                ):
                    if src_key in d and d[src_key] is not None:
                        edge[dst_key] = d[src_key]
                edge_path.append(edge)

            if ok and edge_path:
                scored.append(
                    (score, len(node_seq), "->".join(node_seq), edge_path)
                )

        scored.sort(key=lambda x: (-x[0], x[1], x[2]))
        return [ep for _, _, _, ep in scored[:max_paths]]


# -------------------- schema validation --------------------- #


def _validate(
    nodes: list[dict], edges: list[dict], node_by_id: dict[str, dict],
) -> None:
    """Check the seed KG for structural bugs. Collects *all* offenders and
    raises KGValidationError with the full list -- failing loud, not at first
    (addresses H3 in the audit plan)."""
    errors: list[str] = []

    seen_ids: set[str] = set()
    # (node_type, namespace, external_id) -> first canonical_id seen
    xref_owner: dict[tuple[str, str, str], str] = {}

    for i, n in enumerate(nodes):
        nid = n.get("id")
        name = n.get("name")
        ntype = n.get("type")
        if not nid or not isinstance(nid, str):
            errors.append(f"nodes[{i}]: missing or non-string 'id'")
            continue
        if nid in seen_ids:
            errors.append(f"node '{nid}': duplicate id")
        seen_ids.add(nid)
        if not name or not isinstance(name, str):
            errors.append(f"node '{nid}': missing or non-string 'name'")
        if ntype not in KNOWN_NODE_TYPES:
            errors.append(
                f"node '{nid}': type {ntype!r} not in "
                f"{sorted(KNOWN_NODE_TYPES)}"
            )

        xrefs = n.get("xrefs") or {}
        for ns, ext in xrefs.items():
            if ext is None or ns not in _XREF_NAMESPACES:
                continue
            key = (ntype or "?", ns, str(ext))
            prev = xref_owner.get(key)
            if prev is not None and prev != nid:
                errors.append(
                    f"xref collision: {ntype} nodes '{prev}' and '{nid}' "
                    f"both claim {ns}='{ext}'"
                )
            else:
                xref_owner[key] = nid

    triple_set: set[tuple[str, str, str]] = set()
    for i, e in enumerate(edges):
        h, r, t = e.get("head"), e.get("rel"), e.get("tail")
        if not (isinstance(h, str) and h and isinstance(r, str) and r
                and isinstance(t, str) and t):
            errors.append(
                f"edges[{i}]: head/rel/tail must be non-empty strings "
                f"(got head={h!r}, rel={r!r}, tail={t!r})"
            )
            continue
        if h not in node_by_id:
            errors.append(f"edges[{i}] {h}-{r}->{t}: head '{h}' not in nodes")
        if t not in node_by_id:
            errors.append(f"edges[{i}] {h}-{r}->{t}: tail '{t}' not in nodes")
        if r not in KNOWN_RELATIONS:
            errors.append(
                f"edges[{i}] {h}-{r}->{t}: relation {r!r} not in "
                f"{sorted(KNOWN_RELATIONS)}"
            )
        key = (h, r, t)
        if key in triple_set:
            errors.append(f"duplicate triple: ({h}, {r}, {t})")
        triple_set.add(key)
        if r == "TREATS":
            yr = e.get("approval_year")
            if not isinstance(yr, int):
                errors.append(
                    f"TREATS edge {h}->{t}: 'approval_year' must be int "
                    f"(got {yr!r})"
                )

    if errors:
        preview = "\n  - ".join(errors[:25])
        more = "" if len(errors) <= 25 else f"\n  (+{len(errors) - 25} more)"
        raise KGValidationError(
            f"KG JSON failed schema validation "
            f"({len(errors)} issue{'s' if len(errors) != 1 else ''}):\n"
            f"  - {preview}{more}"
        )


# -------------------- loader --------------------- #


def load_kg(path: Path | str = DEFAULT_KG_PATH) -> KG:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = payload["nodes"]
    edges = payload["edges"]

    node_by_id: dict[str, dict] = {n["id"]: n for n in nodes if "id" in n}
    _validate(nodes, edges, node_by_id)

    G = nx.MultiDiGraph()
    for n in nodes:
        G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
    for e in edges:
        G.add_edge(
            e["head"], e["tail"],
            **{k: v for k, v in e.items() if k not in ("head", "tail")},
        )

    # Compact integer indexes. Sorted for reproducibility across runs.
    entities = sorted(node_by_id.keys())
    relations = sorted({e["rel"] for e in edges})
    entity_to_idx = {e: i for i, e in enumerate(entities)}
    relation_to_idx = {r: i for i, r in enumerate(relations)}
    triples = [
        (entity_to_idx[e["head"]], relation_to_idx[e["rel"]],
         entity_to_idx[e["tail"]])
        for e in edges
    ]

    drugs    = sorted(n["id"] for n in nodes if n["type"] == "Drug")
    diseases = sorted(n["id"] for n in nodes if n["type"] == "Disease")
    symptoms = sorted(n["id"] for n in nodes if n["type"] == "Symptom")

    # O(1) lookup: is this (drug, disease) already an approved TREATS edge,
    # and what was its approval year? Replaces per-request linear scans in
    # api/services/repurpose.py (fix for H2).
    treats_edge: dict[tuple[str, str], dict] = {}
    for e in edges:
        if e["rel"] == "TREATS":
            treats_edge[(e["head"], e["tail"])] = e

    # Case-normalized reverse xref index: external id -> canonical id. Also
    # accepts the canonical id itself, so callers do not need a special path.
    xref_index: dict[str, str] = {}
    for n in nodes:
        cid = n["id"]
        xref_index[cid.upper()] = cid
        for ns, ext in (n.get("xrefs") or {}).items():
            if ext is None or ns not in _XREF_NAMESPACES:
                continue
            xref_index[str(ext).strip().upper()] = cid

    return KG(
        version=payload.get("version", "unknown"),
        graph=G,
        node_by_id=node_by_id,
        entity_to_idx=entity_to_idx,
        idx_to_entity=entities,
        relation_to_idx=relation_to_idx,
        idx_to_relation=relations,
        triples=triples,
        triples_with_props=edges,
        drugs=drugs,
        diseases=diseases,
        symptoms=symptoms,
        treats_edge=treats_edge,
        xref_index=xref_index,
    )


if __name__ == "__main__":
    kg = load_kg()
    print(f"Loaded KG {kg.version}: {len(kg.idx_to_entity)} entities, "
          f"{len(kg.idx_to_relation)} relations, {len(kg.triples)} triples")
    print(f"  drugs={len(kg.drugs)}  diseases={len(kg.diseases)}  "
          f"symptoms={len(kg.symptoms)}")
    print(f"  treats_edge: {len(kg.treats_edge)}  "
          f"xref_index: {len(kg.xref_index)}")
    npc = kg.node("D:NPC")
    if npc:
        print("NPC node:", npc["name"], "xrefs=", npc.get("xrefs"))
    print("resolve MONDO:0018982 ->", kg.resolve_external_id("MONDO:0018982"))
    print("resolve hp:0001250   ->", kg.resolve_external_id("hp:0001250"))
    sub = kg.subgraph_around("D:NPC", k=2, max_nodes=50)
    print(f"2-hop subgraph around NPC: {len(sub['nodes'])} nodes, "
          f"{len(sub['edges'])} edges")
    paths = kg.evidence_paths("DR:AMBROXOL", "D:GAUCHER", k=3, max_paths=5)
    print(f"Ambroxol -> Gaucher evidence paths: {len(paths)}")
    for p in paths[:3]:
        chain = " -> ".join(
            f"[{x['rel']}:{x['direction']}] {x['to']}" for x in p
        )
        print(f"  {p[0]['from']} {chain}")

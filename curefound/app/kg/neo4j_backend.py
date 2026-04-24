"""
Neo4j KG backend.

Implements the KGBackend protocol using Cypher queries over a Bolt connection.
This is the Phase 1 Step 5 backend — it populates the same accessor surface
as the NetworkX KG dataclass so all routes and services work unchanged.

Startup cost: at __init__ time we run a handful of Cypher queries to
materialise the Python-side caches that TransE scoring and the repurpose
service expect (idx_to_entity, treats_edge, etc.). These are immutable once
the graph is loaded, so the cost is paid once at lifespan startup.

Lazy import: `neo4j` is not a required dependency for the default
KG_BACKEND=networkx path. We import it only inside __init__ so that
`python -c 'import app'` still works without neo4j installed.

Usage (set KG_BACKEND=neo4j in .env):
    from app.kg.neo4j_backend import Neo4jBackend
    backend = Neo4jBackend(uri, user, password, database)
    # Neo4jBackend satisfies KGBackend protocol
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Iterable

from app.core.logging import get_logger

_log = get_logger(__name__)

# Semantic weights — mirrors loader.py _REL_WEIGHT for consistent path scoring
_REL_WEIGHT = {
    "TARGETS": 3.0,
    "CAUSES": 3.0,
    "ENCODES": 2.5,
    "TREATS": 2.5,
    "ASSOCIATED_WITH": 2.0,
    "PARTICIPATES_IN": 1.5,
    "HAS_PHENOTYPE": 1.0,
}


class Neo4jBackend:
    """KGBackend implementation backed by Neo4j 5.

    Requires the `neo4j` Python driver (pip install neo4j>=5).

    All KGBackend protocol attributes are materialised at __init__ time so
    that services can access them synchronously without holding a driver
    connection open per request.
    """

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
    ) -> None:
        try:
            from neo4j import GraphDatabase  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "neo4j Python driver not installed. "
                "Run `pip install 'neo4j>=5'` or set KG_BACKEND=networkx."
            ) from exc

        _log.info("neo4j_backend.connect", uri=uri, db=database)
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database

        # Verify connectivity before spending startup time on cache build
        self._driver.verify_connectivity()
        _log.info("neo4j_backend.connected")

        t0 = time.monotonic()
        self._build_caches()
        _log.info(
            "neo4j_backend.caches_built",
            elapsed_s=round(time.monotonic() - t0, 1),
            n_entities=len(self._idx_to_entity),
            n_triples=len(self._triples),
        )

    def close(self) -> None:
        self._driver.close()

    # ---------------------------------------------------------------------- #
    # Cache builders                                                          #
    # ---------------------------------------------------------------------- #

    def _run(self, query: str, **params):  # type: ignore[return]
        with self._driver.session(database=self._database) as sess:
            return list(sess.run(query, **params))

    def _build_caches(self) -> None:
        """Run Cypher queries to populate all Python-side lookup tables."""

        # ---- nodes ---- #
        _log.info("neo4j_backend.loading_nodes")
        node_rows = self._run(
            """
            MATCH (n)
            WHERE n.id IS NOT NULL
            RETURN n.id AS id, n.name AS name, labels(n)[0] AS type,
                   properties(n) AS props
            ORDER BY n.id
            """
        )

        node_by_id: dict[str, dict] = {}
        xref_index: dict[str, str] = {}
        drugs: list[str] = []
        diseases: list[str] = []
        symptoms: list[str] = []

        for r in node_rows:
            nid: str = r["id"]
            ntype: str = r["type"]
            props: dict = dict(r["props"])
            # Build clean node dict (Neo4j returns all properties in props)
            name = props.get("name", r.get("name", ""))
            xrefs: dict = {}
            for k, v in props.items():
                if k.endswith("_id") and k != "id" and v:
                    xrefs[k] = v
            node = {"id": nid, "name": name, "type": ntype, "xrefs": xrefs}
            # Copy optional flags
            for flag in ("is_rare", "approval_year", "is_approved", "inheritance"):
                if flag in props:
                    node[flag] = props[flag]
            node_by_id[nid] = node

            # xref_index: canonical id + all xrefs -> canonical id
            xref_index[nid.upper()] = nid
            for v in xrefs.values():
                if v:
                    xref_index[str(v).strip().upper()] = nid

            if ntype == "Drug":
                drugs.append(nid)
            elif ntype == "Disease":
                diseases.append(nid)
            elif ntype == "Symptom":
                symptoms.append(nid)

        self._node_by_id = node_by_id
        self._xref_index = xref_index
        self._drugs = sorted(drugs)
        self._diseases = sorted(diseases)
        self._symptoms = sorted(symptoms)

        # ---- entity / relation indexes (for TransE) ---- #
        self._idx_to_entity: list[str] = sorted(node_by_id.keys())
        self._entity_to_idx: dict[str, int] = {
            e: i for i, e in enumerate(self._idx_to_entity)
        }

        # ---- edges ---- #
        _log.info("neo4j_backend.loading_edges")
        edge_rows = self._run(
            """
            MATCH (h)-[r]->(t)
            WHERE h.id IS NOT NULL AND t.id IS NOT NULL
            RETURN h.id AS head, type(r) AS rel, t.id AS tail,
                   properties(r) AS props
            ORDER BY h.id, type(r), t.id
            """
        )

        relations_set: set[str] = set()
        triples_with_props: list[dict] = []
        treats_edge: dict[tuple[str, str], dict] = {}

        for r in edge_rows:
            head: str = r["head"]
            rel: str = r["rel"]
            tail: str = r["tail"]
            props: dict = dict(r["props"])
            edge = {"head": head, "rel": rel, "tail": tail, **props}
            triples_with_props.append(edge)
            relations_set.add(rel)
            if rel == "TREATS":
                treats_edge[(head, tail)] = edge

        self._triples_with_props = triples_with_props
        self._treats_edge = treats_edge
        self._idx_to_relation: list[str] = sorted(relations_set)
        self._relation_to_idx: dict[str, int] = {
            r: i for i, r in enumerate(self._idx_to_relation)
        }
        e2i = self._entity_to_idx
        r2i = self._relation_to_idx
        self._triples: list[tuple[int, int, int]] = [
            (e2i[e["head"]], r2i[e["rel"]], e2i[e["tail"]])
            for e in triples_with_props
            if e["head"] in e2i and e["rel"] in r2i and e["tail"] in e2i
        ]

        # ---- KG version ---- #
        ver_rows = self._run(
            "MATCH (m:_Meta) RETURN m.version AS version LIMIT 1"
        )
        self._version = ver_rows[0]["version"] if ver_rows else "neo4j-unknown"

    # ---------------------------------------------------------------------- #
    # KGBackend protocol — metadata                                           #
    # ---------------------------------------------------------------------- #

    @property
    def version(self) -> str:
        return self._version

    # ---------------------------------------------------------------------- #
    # KGBackend protocol — indexes                                            #
    # ---------------------------------------------------------------------- #

    @property
    def idx_to_entity(self) -> list[str]:
        return self._idx_to_entity

    @property
    def entity_to_idx(self) -> dict[str, int]:
        return self._entity_to_idx

    @property
    def idx_to_relation(self) -> list[str]:
        return self._idx_to_relation

    @property
    def relation_to_idx(self) -> dict[str, int]:
        return self._relation_to_idx

    @property
    def triples(self) -> list[tuple[int, int, int]]:
        return self._triples

    @property
    def triples_with_props(self) -> list[dict]:
        return self._triples_with_props

    # ---------------------------------------------------------------------- #
    # KGBackend protocol — entity lists                                       #
    # ---------------------------------------------------------------------- #

    @property
    def drugs(self) -> list[str]:
        return self._drugs

    @property
    def diseases(self) -> list[str]:
        return self._diseases

    @property
    def symptoms(self) -> list[str]:
        return self._symptoms

    # ---------------------------------------------------------------------- #
    # KGBackend protocol — lookup tables                                      #
    # ---------------------------------------------------------------------- #

    @property
    def node_by_id(self) -> dict[str, dict]:
        return self._node_by_id

    @property
    def treats_edge(self) -> dict[tuple[str, str], dict]:
        return self._treats_edge

    # ---------------------------------------------------------------------- #
    # KGBackend protocol — accessor methods                                   #
    # ---------------------------------------------------------------------- #

    def node(self, node_id: str) -> dict | None:
        return self._node_by_id.get(node_id)

    def resolve_external_id(self, ext_id: str) -> str | None:
        if not ext_id or not isinstance(ext_id, str):
            return None
        return self._xref_index.get(ext_id.strip().upper())

    def search(
        self,
        query: str,
        types: Iterable[str] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Substring search via in-memory scan of the node cache.

        For the seed MVP this is fast enough (<5 ms for ~1k nodes).
        Phase 3 replaces this with the FTS index on Neo4j once the full
        PrimeKG graph makes in-memory scan infeasible.
        """
        q = query.strip().lower()
        if not q:
            return []
        types_set = set(types) if types else None
        out: list[tuple[tuple[int, int, str], dict]] = []
        for n in self._node_by_id.values():
            if types_set and n["type"] not in types_set:
                continue
            name = n["name"].lower()
            if q not in name:
                continue
            if name == q:
                score = 0
            elif name.startswith(q):
                score = 1
            else:
                score = 2
            out.append(((score, len(name), n["id"]), n))
        out.sort(key=lambda x: x[0])
        return [n for _, n in out[:limit]]

    def subgraph_around(
        self,
        node_id: str,
        k: int = 2,
        max_nodes: int = 200,
    ) -> dict:
        """BFS subgraph via Cypher (replaces NetworkX BFS for larger graphs).

        Uses variable-length path traversal capped at k hops. Results are
        sorted for determinism (same as NetworkX backend).
        """
        # For the seed-KG scale, fall back to in-memory BFS using the cached
        # triples_with_props. Phase 3 switches to a pure Cypher query once
        # the PrimeKG graph is loaded.
        if node_id not in self._node_by_id:
            return {"nodes": [], "edges": []}

        # Build adjacency list from triples cache
        adj: dict[str, set[str]] = {}
        for e in self._triples_with_props:
            h, t = e["head"], e["tail"]
            adj.setdefault(h, set()).add(t)
            adj.setdefault(t, set()).add(h)

        visited: set[str] = {node_id}
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])

        while queue and len(visited) < max_nodes:
            cur, dist = queue.popleft()
            if dist >= k:
                continue
            for nb in sorted(adj.get(cur, set())):
                if nb in visited or nb not in self._node_by_id:
                    continue
                if len(visited) >= max_nodes:
                    break
                visited.add(nb)
                queue.append((nb, dist + 1))

        nodes = [
            {
                "data": {
                    "id": nid,
                    "label": self._node_by_id[nid]["name"],
                    "type": self._node_by_id[nid]["type"],
                }
            }
            for nid in sorted(visited)
        ]
        edges: list[dict] = []
        for e in self._triples_with_props:
            u, v = e["head"], e["tail"]
            if u not in visited or v not in visited:
                continue
            payload: dict = {
                "id": f"{u}__{e['rel']}__{v}",
                "source": u,
                "target": v,
                "label": e["rel"],
            }
            for src_k, dst_k in (
                ("approval_year", "approval_year"),
                ("action", "action"),
                ("frequency", "frequency"),
                ("source", "provenance"),
            ):
                if src_k in e and e[src_k] is not None:
                    payload[dst_k] = e[src_k]
            edges.append({"data": payload})

        edges.sort(
            key=lambda ed: (ed["data"]["source"], ed["data"]["target"], ed["data"]["label"])
        )
        return {"nodes": nodes, "edges": edges}

    def evidence_paths(
        self,
        head: str,
        tail: str,
        k: int = 3,
        max_paths: int = 10,
    ) -> list[list[dict]]:
        """Evidence paths via in-memory BFS over triples cache.

        Phase 3 replaces this with a Cypher `shortestPath` / `allShortestPaths`
        query once the full PrimeKG graph makes in-memory enumeration too slow.
        """
        if head not in self._node_by_id or tail not in self._node_by_id:
            return []
        if head == tail:
            return []

        # Build undirected adjacency using triples
        fwd: dict[str, list[dict]] = {}  # (u, v) -> list of edge dicts
        rev: dict[str, list[dict]] = {}
        for e in self._triples_with_props:
            h, t = e["head"], e["tail"]
            fwd.setdefault(h, [])
            fwd[h].append(e)
            rev.setdefault(t, [])
            rev[t].append(e)

        # DFS / BFS simple path enumeration (capped)
        def get_neighbors(node: str) -> list[str]:
            out_nodes = [e["tail"] for e in fwd.get(node, [])]
            in_nodes = [e["head"] for e in rev.get(node, [])]
            return sorted(set(out_nodes + in_nodes))

        results: list[tuple[float, int, str, list[dict]]] = []
        seen_seqs: set[tuple[str, ...]] = set()

        stack: list[tuple[list[str], float]] = [([head], 0.0)]
        candidate_limit = 200

        while stack and len(results) < candidate_limit:
            path_nodes, score = stack.pop()
            cur = path_nodes[-1]

            if cur == tail and len(path_nodes) > 1:
                seq = tuple(path_nodes)
                if seq not in seen_seqs:
                    seen_seqs.add(seq)
                    edge_path = self._nodes_to_edge_path(path_nodes, fwd, rev)
                    if edge_path:
                        results.append((score, len(path_nodes), "->".join(path_nodes), edge_path))
                continue

            if len(path_nodes) > k + 1:
                continue

            for nb in get_neighbors(cur):
                if nb not in path_nodes:
                    # Estimate score increment
                    all_edges = fwd.get(cur, []) + [
                        e for e in rev.get(nb, []) if e["head"] == nb and e["tail"] == cur
                    ]
                    best_weight = max(
                        (_REL_WEIGHT.get(e.get("rel", ""), 0.5) for e in all_edges),
                        default=0.5,
                    )
                    stack.append(([*path_nodes, nb], score + best_weight))

        results.sort(key=lambda x: (-x[0], x[1], x[2]))
        return [ep for _, _, _, ep in results[:max_paths]]

    @staticmethod
    def _nodes_to_edge_path(
        node_seq: list[str],
        fwd: dict[str, list[dict]],
        rev: dict[str, list[dict]],
    ) -> list[dict]:
        """Convert a node sequence to a list of edge dicts."""
        from itertools import pairwise  # type: ignore[attr-defined]

        path: list[dict] = []
        for a, b in pairwise(node_seq):
            fwd_edges = [e for e in fwd.get(a, []) if e["tail"] == b]
            rev_edges = [e for e in rev.get(a, []) if e["head"] == b]
            if fwd_edges:
                d = max(fwd_edges, key=lambda e: _REL_WEIGHT.get(e.get("rel", ""), 0.5))
                direction = "forward"
            elif rev_edges:
                d = max(rev_edges, key=lambda e: _REL_WEIGHT.get(e.get("rel", ""), 0.5))
                direction = "reverse"
            else:
                return []  # broken path
            rel = d.get("rel")
            if not rel:
                return []
            hop: dict = {"from": a, "to": b, "rel": rel, "direction": direction}
            for sk, dk in (("approval_year", "approval_year"), ("source", "provenance")):
                if sk in d and d[sk] is not None:
                    hop[dk] = d[sk]
            path.append(hop)
        return path

"""
KGBackend protocol — the accessor surface shared by NetworkX and Neo4j backends.

Design rationale
----------------
The current KG dataclass (app.kg.loader.KG) is the NetworkX-in-memory backend.
Phase 1 Step 5 introduces a Neo4j backend that runs the same queries over
Bolt. Rather than forcing both backends to subclass the same ABC (which would
require Neo4jBackend to materialise Python lists for all 8M PrimeKG edges),
we define a `runtime_checkable` Protocol. Both backends satisfy it structurally:
the NetworkX backend because KG already has these methods; the Neo4j backend
because neo4j_backend.py implements the same signatures.

Callers (routers, services, tests) only need `KGBackend` as a type annotation.
`isinstance(obj, KGBackend)` returns True at runtime for any object that
exposes all required attributes — no explicit registration needed.

Attribute notes
---------------
- `graph` is NetworkX-only. Routes/services that need it (degree counts,
  BFS-based evidence paths) must check `hasattr(backend, "graph")` or
  call the method equivalents below. Phase 3 will add Cypher-based
  `evidence_paths()` to Neo4jBackend so `graph` access disappears from
  hot paths entirely.

- `triples` / `triples_with_props` return the full edge list. For the
  Neo4j backend these are lazy-loaded at startup and cached (a full Bolt
  round-trip per request would be too slow for TransE scoring).

- `treats_edge` is a dict keyed by `(drug_id, disease_id)`. The Neo4j
  backend materialises this at startup by running a single Cypher query
  `MATCH (d:Drug)-[r:TREATS]->(dis:Disease) RETURN ...`.

Extending the protocol
----------------------
Add a new method to `KGBackend` and implement it in both backends.
Then add a regression test that calls the method against both backends.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    # Imported only for type-checker: avoids circular imports at runtime.
    pass


@runtime_checkable
class KGBackend(Protocol):
    """Structural protocol for KG accessor backends.

    Any object that exposes all of these attributes and methods satisfies
    the protocol -- no inheritance required.
    """

    # ---- Metadata ---- #

    @property
    def version(self) -> str:
        """A short content-hash version string, e.g. 'kg-mvp-0.1+sha.abc123'."""
        ...

    # ---- Entity / relation indexes (needed by TransE scoring) ---- #

    @property
    def idx_to_entity(self) -> list[str]:
        """Sorted list of canonical entity ids. Index = TransE entity index."""
        ...

    @property
    def entity_to_idx(self) -> dict[str, int]:
        """Reverse of idx_to_entity."""
        ...

    @property
    def idx_to_relation(self) -> list[str]:
        """Sorted list of canonical relation labels."""
        ...

    @property
    def relation_to_idx(self) -> dict[str, int]:
        """Reverse of idx_to_relation."""
        ...

    @property
    def triples(self) -> list[tuple[int, int, int]]:
        """All (head_idx, rel_idx, tail_idx) integer triples."""
        ...

    @property
    def triples_with_props(self) -> list[dict]:
        """All edge dicts {head, rel, tail, **props}."""
        ...

    # ---- Convenience entity lists ---- #

    @property
    def drugs(self) -> list[str]:
        """Sorted canonical ids of all Drug nodes."""
        ...

    @property
    def diseases(self) -> list[str]:
        """Sorted canonical ids of all Disease nodes."""
        ...

    @property
    def symptoms(self) -> list[str]:
        """Sorted canonical ids of all Symptom nodes."""
        ...

    # ---- Lookup tables ---- #

    @property
    def node_by_id(self) -> dict[str, dict]:
        """Canonical id -> node dict. Includes all nodes."""
        ...

    @property
    def treats_edge(self) -> dict[tuple[str, str], dict]:
        """(drug_id, disease_id) -> TREATS edge dict (for approval-year lookup)."""
        ...

    # ---- Accessor methods ---- #

    def node(self, node_id: str) -> dict | None:
        """Return node dict for `node_id`, or None if not found."""
        ...

    def resolve_external_id(self, ext_id: str) -> str | None:
        """Map an external id (MONDO:..., HP:..., HGNC:...) to a canonical id.
        Case-insensitive. Returns None on miss. Accepts canonical ids too."""
        ...

    def search(
        self,
        query: str,
        types: Iterable[str] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Substring search on node names. Deterministic ordering."""
        ...

    def subgraph_around(
        self,
        node_id: str,
        k: int = 2,
        max_nodes: int = 200,
    ) -> dict:
        """BFS k-hop subgraph. Returns Cytoscape-friendly {nodes, edges}."""
        ...

    def evidence_paths(
        self,
        head: str,
        tail: str,
        k: int = 3,
        max_paths: int = 10,
    ) -> list[list[dict]]:
        """Find semantically-ranked simple paths head -> tail of length <= k."""
        ...

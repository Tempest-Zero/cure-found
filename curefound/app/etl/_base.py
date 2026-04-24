"""
Ingestor ABC + shared data types.

Every Phase 1 data-source ingestor (PrimeKG, DrugCentral, HPO, Orphanet,
Reactome) inherits from `Ingestor` and implements `required_files()` and
`run()`. The ABC provides checkpoint load/save so reruns skip already-
processed sources.

Checkpoint protocol
-------------------
A checkpoint is a JSON file at `{raw_dir}/{name}/.checkpoint.json` containing
the keys below. `load_checkpoint()` returns `None` when no checkpoint exists
or when the stamp is stale (source files were modified since).

    {"done": true, "n_nodes": 42, "n_edges": 123, "finished_at": "2025-..."}

Usage inside an ingestor:
    ckpt = self.load_checkpoint(settings)
    if ckpt and ckpt.get("done"):
        # return cached result instead of re-running
        ...
    ...heavy work...
    self.save_checkpoint(settings, n_nodes=..., n_edges=...)
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger

_log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Output types                                                                #
# --------------------------------------------------------------------------- #


@dataclass
class IngestorStats:
    n_nodes_added: int = 0
    n_edges_added: int = 0
    n_nodes_skipped: int = 0
    n_edges_skipped: int = 0
    elapsed_s: float = 0.0
    source: str = ""


@dataclass
class IngestionOutput:
    """Nodes and edges produced by a single ingestor run."""

    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    stats: IngestorStats = field(default_factory=IngestorStats)

    def extend(self, other: IngestionOutput) -> None:
        self.nodes.extend(other.nodes)
        self.edges.extend(other.edges)


# --------------------------------------------------------------------------- #
# Canonical node helpers                                                      #
# --------------------------------------------------------------------------- #

_TYPE_MAP = {
    "disease": "Disease",
    "drug": "Drug",
    "gene/protein": "Gene",
    "gene": "Gene",
    "protein": "Protein",
    "pathway": "Pathway",
    "phenotype": "Symptom",
    "symptom": "Symptom",
    "biological_process": "Pathway",
    "molecular_function": "Pathway",
    "cellular_component": "Pathway",
    "anatomy": "Pathway",  # treat anatomy as context, map to Gene/Protein domain
}


def normalize_node_type(raw_type: str) -> str | None:
    """Map a source-specific node type string to one of our canonical types.
    Returns None if the type is not in scope (caller should skip that node)."""
    return _TYPE_MAP.get(raw_type.lower().strip())


def make_canonical_id(node_type: str, source_ns: str, source_id: str) -> str:
    """Generate a deterministic canonical id from a node type + external id.

    Pattern: `{PREFIX}:{slug}` where slug = source_id upper-cased and
    sanitized (spaces -> underscores, non-alphanumeric stripped).

    Examples:
        Disease + MONDO:0018982  -> D:MONDO_0018982  (or D:GAUCHER if we patch)
        Drug + DB01048           -> DR:DB01048
        Gene/Protein + NCBI:2629 -> G:2629
        Symptom + HP:0001250     -> S:HP_0001250
        Pathway + REACTOME:R-HSA -> PW:R_HSA
    """
    prefixes = {
        "Disease": "D",
        "Drug": "DR",
        "Gene": "G",
        "Protein": "P",
        "Pathway": "PW",
        "Symptom": "S",
    }
    prefix = prefixes.get(node_type, "X")
    # Keep namespace in slug to avoid collisions across sources.
    if source_ns and source_ns.upper() not in source_id.upper():
        slug = f"{source_ns.upper()}_{source_id}"
    else:
        slug = source_id
    # Sanitize: keep alphanumeric + underscore + dot, uppercase.
    slug = "".join(c if c.isalnum() or c in "._-" else "_" for c in slug).upper()
    slug = slug.strip("_")
    return f"{prefix}:{slug}"


# --------------------------------------------------------------------------- #
# KG writer (shared de-dup accumulator)                                      #
# --------------------------------------------------------------------------- #


class KGAccumulator:
    """Accumulates nodes and edges from multiple ingestor passes,
    de-duplicating by canonical id (nodes) and (head, rel, tail) (edges).

    Merge rules:
    - Nodes: later write wins for top-level fields; xrefs are *merged* (new
      namespace keys added, existing keys left unchanged so authoritative
      sources are not clobbered by PrimeKG guesses).
    - Edges: for TREATS edges, DrugCentral wins over PrimeKG (DrugCentral
      has `approval_year`). For all other edges, first-write wins.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, dict] = {}
        self._edges: dict[tuple[str, str, str], dict] = {}

    # ---- nodes ---- #

    def add_node(self, node: dict, *, overwrite: bool = False) -> bool:
        nid = node.get("id")
        if not nid:
            return False
        if nid in self._nodes:
            if overwrite:
                existing_xrefs = self._nodes[nid].get("xrefs") or {}
                new_xrefs = node.get("xrefs") or {}
                merged_xrefs = {**new_xrefs, **existing_xrefs}  # existing wins
                self._nodes[nid] = {**node, "xrefs": merged_xrefs}
            else:
                # Merge xrefs only
                existing_xrefs = self._nodes[nid].get("xrefs") or {}
                new_xrefs = node.get("xrefs") or {}
                for ns, val in new_xrefs.items():
                    if ns not in existing_xrefs and val is not None:
                        existing_xrefs[ns] = val
                self._nodes[nid]["xrefs"] = existing_xrefs
            return False  # not a new node
        self._nodes[nid] = node
        return True

    def add_nodes(self, nodes: list[dict], *, overwrite: bool = False) -> int:
        return sum(1 for n in nodes if self.add_node(n, overwrite=overwrite))

    # ---- edges ---- #

    def add_edge(self, edge: dict, *, priority: int = 0) -> bool:
        """Add an edge. Higher `priority` wins over lower for the same triple.
        Priority: DrugCentral=10, PrimeKG=5, seed=0.
        """
        h, r, t = edge.get("head"), edge.get("rel"), edge.get("tail")
        if not (h and r and t):
            return False
        key = (h, r, t)
        if key in self._edges:
            existing_priority = self._edges[key].get("_priority", 0)
            if priority > existing_priority:
                self._edges[key] = {**edge, "_priority": priority}
            return False
        self._edges[key] = {**edge, "_priority": priority}
        return True

    def add_edges(self, edges: list[dict], *, priority: int = 0) -> int:
        return sum(1 for e in edges if self.add_edge(e, priority=priority))

    # ---- output ---- #

    def to_output(self) -> dict:
        nodes = list(self._nodes.values())
        # Strip internal priority tag before writing
        edges = [
            {k: v for k, v in e.items() if k != "_priority"} for e in self._edges.values()
        ]
        return {"nodes": nodes, "edges": edges}

    @property
    def n_nodes(self) -> int:
        return len(self._nodes)

    @property
    def n_edges(self) -> int:
        return len(self._edges)


# --------------------------------------------------------------------------- #
# Base class                                                                  #
# --------------------------------------------------------------------------- #


class Ingestor(ABC):
    """Abstract base for a Phase 1 data-source ingestor."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short lowercase identifier, e.g. 'primekg', 'hpo'."""
        ...

    @property
    @abstractmethod
    def priority(self) -> int:
        """Edge priority for de-duplication. Higher wins. DrugCentral=10,
        PrimeKG=5, HPO=7, Orphanet=6, Reactome=6."""
        ...

    @abstractmethod
    def required_files(self, settings: Settings) -> list[Path]:
        """List of raw data files that must exist before `run()` is called.
        If any is missing, `run()` should raise FileNotFoundError."""
        ...

    @abstractmethod
    def run(self, settings: Settings) -> IngestionOutput:
        """Execute the ingestor. Should be idempotent."""
        ...

    # ---- checkpoint helpers ---- #

    def checkpoint_path(self, settings: Settings) -> Path:
        return settings.raw_dir / self.name / ".checkpoint.json"

    def load_checkpoint(self, settings: Settings) -> dict[str, Any] | None:
        ckpt_path = self.checkpoint_path(settings)
        if not ckpt_path.exists():
            return None
        try:
            ckpt: dict[str, Any] = json.loads(ckpt_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not ckpt.get("done"):
            return None
        # Invalidate if any required source file is newer than the checkpoint
        ckpt_mtime = ckpt_path.stat().st_mtime
        for f in self.required_files(settings):
            if f.exists() and f.stat().st_mtime > ckpt_mtime:
                _log.info(
                    "ingestor.checkpoint_stale",
                    source=self.name,
                    file=str(f),
                )
                return None
        return ckpt

    def save_checkpoint(self, settings: Settings, **extra: Any) -> None:
        ckpt_path = self.checkpoint_path(settings)
        ckpt_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "done": True,
            "source": self.name,
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **extra,
        }
        ckpt_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ---- convenience ---- #

    def check_required_files(self, settings: Settings) -> None:
        missing = [f for f in self.required_files(settings) if not f.exists()]
        if missing:
            paths = "\n  ".join(str(f) for f in missing)
            raise FileNotFoundError(
                f"[{self.name}] Required files are missing. "
                f"Run `python -m app.etl.fetch_all --source {self.name}` first.\n  {paths}"
            )

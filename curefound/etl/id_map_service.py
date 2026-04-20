"""
Canonical ID mapping service.

MVP: a thin wrapper around the seed KG's xrefs — every node knows its
external xrefs (mondo_id, hgnc_id, uniprot_id, drugcentral_id, hpo_id,
reactome_id), and we build a reverse index at load time.

Phase 1: replace with MONDO SSSOM + HGNC + UniProt ID mapping + OXO +
Bioregistry (see plan). The public interface below stays stable:
    canonicalize(source_id, source_namespace) -> canonical_id | None
    xref(canonical_id, namespace)             -> source_id | None

See plan.md section "Canonical ID scheme" for the target per-entity scheme.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# Canonical namespaces supported by the MVP seed KG.
SUPPORTED_NAMESPACES = {
    "mondo_id", "omim_id", "orpha_id",            # Disease
    "hgnc_id", "ncbi_gene_id",                    # Gene
    "uniprot_id",                                 # Protein
    "drugcentral_id", "chembl_id", "pubchem_cid", # Drug
    "reactome_id", "kegg_id",                     # Pathway
    "hpo_id",                                     # Symptom
}


@dataclass
class IdMapService:
    forward: dict[tuple[str, str], str]  # (namespace, external_id) -> canonical_id
    node_xrefs: dict[str, dict[str, str]]  # canonical_id -> {namespace: external_id}

    def canonicalize(self, source_id: str, source_namespace: str) -> str | None:
        """Return the canonical_id for an external id, or None if unmapped.
        `source_namespace` must be in SUPPORTED_NAMESPACES (e.g. "mondo_id")."""
        if source_namespace not in SUPPORTED_NAMESPACES:
            raise ValueError(f"Unsupported namespace: {source_namespace!r}. "
                             f"Known: {sorted(SUPPORTED_NAMESPACES)}")
        return self.forward.get((source_namespace, source_id))

    def xref(self, canonical_id: str, namespace: str) -> str | None:
        """Reverse direction: canonical_id -> external id in a given namespace."""
        return self.node_xrefs.get(canonical_id, {}).get(namespace)

    def all_xrefs(self, canonical_id: str) -> dict[str, str]:
        return dict(self.node_xrefs.get(canonical_id, {}))


def build_from_nodes(nodes: Iterable[dict]) -> IdMapService:
    forward: dict[tuple[str, str], str] = {}
    node_xrefs: dict[str, dict[str, str]] = {}
    for n in nodes:
        canonical_id = n["id"]
        xrefs = n.get("xrefs") or {}
        node_xrefs[canonical_id] = xrefs
        for ns, ext_id in xrefs.items():
            if ext_id is None or ns not in SUPPORTED_NAMESPACES:
                continue
            # In a real system, log collisions. MVP: last writer wins.
            forward[(ns, str(ext_id))] = canonical_id
    return IdMapService(forward=forward, node_xrefs=node_xrefs)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from kg.loader import load_kg

    kg = load_kg()
    svc = build_from_nodes(kg.node_by_id.values())
    print("Canonicalize MONDO:0009937 ->", svc.canonicalize("MONDO:0009937", "mondo_id"))
    print("Canonicalize HP:0001250   ->", svc.canonicalize("HP:0001250",   "hpo_id"))
    print("Canonicalize HGNC:4177    ->", svc.canonicalize("HGNC:4177",    "hgnc_id"))
    print("Canonicalize UNKNOWN      ->", svc.canonicalize("FOO:123",      "mondo_id"))
    print("xrefs for D:GAUCHER       ->", svc.all_xrefs("D:GAUCHER"))

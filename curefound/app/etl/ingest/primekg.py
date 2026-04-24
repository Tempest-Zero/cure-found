"""
PrimeKG ingestor.

PrimeKG (Precision Medicine Knowledge Graph) is a large heterogeneous graph
from Chandak et al. (2023) available at:
    https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/IXA7BM

Files consumed
--------------
  data/raw/primekg/kg.csv              — edge list (~8M rows)
  data/raw/primekg/drug_features.csv   — drug metadata (DrugBank IDs, names)
  data/raw/primekg/disease_features.csv — disease metadata (MONDO, OMIM, DOID)

What this ingestor does
-----------------------
1. Reads kg.csv row-by-row (streaming, never loads full 4 GB into RAM).
2. Applies the LSD disease scope filter: keep only nodes reachable within
   2 hops from an LSD-seed disease.
3. Maps PrimeKG relation types to our 12-relation canonical vocabulary.
4. Generates canonical IDs using the source namespaces.
5. Merges disease/drug metadata from the feature CSV files.

LSD seed diseases (MONDO IDs, matched against disease_features.csv):
    Gaucher: MONDO:0018982
    Niemann-Pick type C: MONDO:0009937
    Niemann-Pick type A/B: MONDO:0015568
    Fabry: MONDO:0010526
    Pompe: MONDO:0009290
    MPS I (Hurler): MONDO:0010001
    MPS II (Hunter): MONDO:0010369
    MPS III (Sanfilippo): MONDO:0016523
    MPS IV (Morquio): MONDO:0007759
    MPS VI (Maroteaux-Lamy): MONDO:0009661
    Krabbe: MONDO:0009499
    Metachromatic leukodystrophy: MONDO:0001521
    GM1 gangliosidosis: MONDO:0009563
    Tay-Sachs: MONDO:0009372
    Batten (NCL): MONDO:0003297
    Cystic fibrosis: MONDO:0009861
    Huntington: MONDO:0007739
    Spinal muscular atrophy: MONDO:0001516
    Duchenne muscular dystrophy: MONDO:0010679

Relation mapping (PrimeKG display_relation -> canonical rel):
    drug_carrier / drug_enzyme / drug_transporter / drug_protein -> TARGETS
    drug_drug -> INTERACTS_WITH
    drug_effect -> SIDE_EFFECT_OF
    indication / off-label use -> TREATS  (authority: DrugCentral > PrimeKG)
    disease_phenotype -> HAS_PHENOTYPE
    disease_protein -> ASSOCIATED_WITH
    protein_disease -> ASSOCIATED_WITH
    bioprocess_protein -> PARTICIPATES_IN  (reversed: protein -> pathway)
    cellular_component_protein -> EXPRESSED_IN
    anatomy_protein -> EXPRESSED_IN
    exposure_protein -> REGULATES
    phenotype_phenotype -> (skipped; not in scope)
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.etl._base import (
    IngestionOutput,
    Ingestor,
    IngestorStats,
    KGAccumulator,
)

if TYPE_CHECKING:
    from app.core.config import Settings

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# LSD seed MONDO IDs (used for disease scope filter)
# ---------------------------------------------------------------------------

LSD_MONDO_SEEDS = frozenset(
    {
        # Core lysosmal storage diseases
        "MONDO:0018982",  # Gaucher
        "MONDO:0009937",  # Niemann-Pick C
        "MONDO:0015568",  # Niemann-Pick A/B
        "MONDO:0010526",  # Fabry
        "MONDO:0009290",  # Pompe
        "MONDO:0010001",  # MPS I Hurler
        "MONDO:0010369",  # MPS II Hunter
        "MONDO:0016523",  # MPS III Sanfilippo
        "MONDO:0007759",  # MPS IVA Morquio A
        "MONDO:0009661",  # MPS VI Maroteaux-Lamy
        "MONDO:0009499",  # Krabbe
        "MONDO:0001521",  # Metachromatic leukodystrophy
        "MONDO:0009563",  # GM1 gangliosidosis
        "MONDO:0009372",  # Tay-Sachs
        "MONDO:0003297",  # Batten (NCL)
        "MONDO:0006816",  # Farber disease
        "MONDO:0008958",  # Wolman disease
        "MONDO:0009543",  # GM2 gangliosidosis (Sandhoff)
        # Extended: common rare diseases for context
        "MONDO:0009861",  # Cystic fibrosis
        "MONDO:0007739",  # Huntington
        "MONDO:0001516",  # Spinal muscular atrophy
        "MONDO:0010679",  # Duchenne muscular dystrophy
        "MONDO:0005027",  # Epilepsy (phenotype context)
        "MONDO:0007947",  # Marfan syndrome
        "MONDO:0018277",  # Wilson disease
        "MONDO:0011399",  # Alpha-1 antitrypsin deficiency
    }
)

# ---------------------------------------------------------------------------
# Relation mapping
# ---------------------------------------------------------------------------

# Maps (PrimeKG relation_type, direction) -> (canonical_rel, reversed)
# `reversed` means x/y need to be swapped to get canonical head/tail.
_REL_MAP: dict[str, tuple[str, bool] | None] = {
    # Drug -> Protein (TARGETS family)
    "carrier": ("TARGETS", False),
    "enzyme": ("TARGETS", False),
    "transporter": ("TARGETS", False),
    "drug_protein": ("TARGETS", False),
    "rev_carrier": None,  # skip — forward is enough
    "rev_enzyme": None,
    "rev_transporter": None,
    "rev_drug_protein": None,
    # Drug -> Disease
    "indication": ("TREATS", False),
    "off-label use": ("TREATS", False),
    "rev_indication": None,
    "rev_off-label use": None,
    # Drug -> Drug
    "drug_drug": ("INTERACTS_WITH", False),
    "rev_drug_drug": None,
    # Drug -> Side effect
    "drug_effect": ("SIDE_EFFECT_OF", False),
    "rev_drug_effect": None,
    # Disease -> Symptom (phenotype)
    "disease_phenotype": ("HAS_PHENOTYPE", False),
    "rev_disease_phenotype": None,
    # Disease -> Gene/Protein  (store as protein -> disease for our canonical)
    "disease_protein": ("ASSOCIATED_WITH", True),   # swap: protein ASSOCIATED_WITH disease
    "rev_disease_protein": ("ASSOCIATED_WITH", False),  # protein ASSOCIATED_WITH disease
    # Protein -> Disease
    "protein_disease": ("ASSOCIATED_WITH", False),
    "rev_protein_disease": None,
    # Pathway -> Protein (store as protein -> pathway)
    "bioprocess_protein": ("PARTICIPATES_IN", True),  # swap: protein PARTICIPATES_IN pathway
    "rev_bioprocess_protein": None,
    # Anatomy/cellular component -> Protein
    "cellular_component_protein": ("EXPRESSED_IN", True),  # swap: protein EXPRESSED_IN location
    "rev_cellular_component_protein": None,
    "anatomy_protein": ("EXPRESSED_IN", True),
    "rev_anatomy_protein": None,
    # Molecular function -> Protein (skip — not in our canonical vocab)
    "molfunc_protein": None,
    "rev_molfunc_protein": None,
    # Phenotype -> Phenotype (skip — not in our canonical vocab yet)
    "phenotype_phenotype": None,
    "rev_phenotype_phenotype": None,
    # Exposure -> Protein
    "exposure_protein": ("REGULATES", True),  # swap: protein REGULATES exposure context
    "rev_exposure_protein": None,
    "exposure_disease": ("ASSOCIATED_WITH", False),
    "rev_exposure_disease": None,
    # Contraindication
    "contraindication": ("CONTRAINDICATED_FOR", False),
    "rev_contraindication": None,
    # Gene -> Gene
    "gene_gene": None,  # skip
    "rev_gene_gene": None,
}

_NODE_TYPE_MAP = {
    "disease": "Disease",
    "drug": "Drug",
    "gene/protein": "Gene",
    "gene": "Gene",
    "protein": "Protein",
    "biological_process": "Pathway",
    "cellular_component": "Pathway",
    "molecular_function": "Pathway",
    "anatomy": "Pathway",
    "phenotype": "Symptom",
    "effect/phenotype": "Symptom",
    "exposure": "Pathway",  # treat as context node
}

_NS_MAP = {
    # PrimeKG x_source -> our xref namespace key
    "MONDO": "mondo_id",
    "OMIM": "omim_id",
    "DOID": "doid_id",
    "DrugBank": "drugbank_id",
    "NCBI": "ncbi_gene_id",
    "UniProt": "uniprot_id",
    "REACTOME": "reactome_id",
    "GO": "go_id",
    "HPO": "hpo_id",
    "ORPHA": "orpha_id",
}


def _source_ns(x_source: str) -> str:
    return _NS_MAP.get(x_source.split(":")[0], "ext_id")


def _node_canonical_id(x_type_raw: str, x_source: str, x_id: str) -> str | None:
    """Generate our canonical ID for a PrimeKG node. Returns None if node type is out of scope."""
    node_type = _NODE_TYPE_MAP.get(x_type_raw.lower().strip())
    if node_type is None:
        return None
    # For diseases: prefer MONDO prefix in ID
    if node_type == "Disease":
        if "MONDO" in x_source.upper():
            return f"D:MONDO_{x_id.replace(':', '_')}"
        if "OMIM" in x_source.upper():
            return f"D:OMIM_{x_id}"
        return f"D:{x_id.replace(':', '_').replace(' ', '_').upper()}"
    if node_type == "Drug":
        if "DrugBank" in x_source or x_id.startswith("DB"):
            return f"DR:{x_id.upper()}"
        return f"DR:{x_id.replace(':', '_').upper()}"
    if node_type == "Gene":
        return f"G:NCBI_{x_id}"
    if node_type == "Protein":
        return f"P:{x_id.upper()}"
    if node_type == "Pathway":
        src = x_source.split(":")[0].upper()
        return f"PW:{src}_{x_id.replace(':', '_').replace(' ', '_').upper()}"
    if node_type == "Symptom":
        if x_id.startswith("HP:"):
            return f"S:{x_id.replace(':', '_')}"
        return f"S:{x_id.replace(':', '_').replace(' ', '_').upper()}"
    return None


def _make_node(x_type_raw: str, x_source: str, x_id: str, x_name: str) -> dict | None:
    node_type = _NODE_TYPE_MAP.get(x_type_raw.lower().strip())
    if node_type is None:
        return None
    cid = _node_canonical_id(x_type_raw, x_source, x_id)
    if cid is None:
        return None
    ns = _source_ns(x_source)
    xrefs: dict[str, str] = {}
    if x_id and ns != "ext_id":
        xrefs[ns] = x_id
    # Also store HPO-style IDs directly for Symptom nodes
    if node_type == "Symptom" and x_id.startswith("HP:"):
        xrefs["hpo_id"] = x_id
    return {"id": cid, "name": x_name, "type": node_type, "xrefs": xrefs}


# ---------------------------------------------------------------------------
# Disease feature file parser (provides MONDO / OMIM / xref enrichment)
# ---------------------------------------------------------------------------


def _load_disease_features(path: Path) -> dict[str, dict]:
    """Parse disease_features.csv. Returns {primekg_node_index: enriched_dict}."""
    if not path.exists():
        return {}
    features: dict[str, dict] = {}
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            idx = row.get("node_index", "")
            if not idx:
                continue
            mondo = row.get("mondo_id", "")
            omim = row.get("omim_ids", "").split(";")[0].strip()  # may be multi
            doid = row.get("doid_id", "")
            name = row.get("node_name", "") or row.get("disease_name", "")
            features[idx] = {
                "mondo_id": mondo or None,
                "omim_id": omim or None,
                "doid_id": doid or None,
                "name": name or None,
            }
    return features


def _load_drug_features(path: Path) -> dict[str, dict]:
    """Parse drug_features.csv. Returns {primekg_node_index: enriched_dict}."""
    if not path.exists():
        return {}
    features: dict[str, dict] = {}
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            idx = row.get("node_index", "")
            if not idx:
                continue
            db_id = row.get("drugbank_id", "") or row.get("drugbank", "")
            pubchem = row.get("pubchem_cid", "")
            chembl = row.get("chembl_id", "")
            name = row.get("node_name", "") or row.get("drug_name", "")
            features[idx] = {
                "drugbank_id": db_id or None,
                "pubchem_cid": pubchem or None,
                "chembl_id": chembl or None,
                "name": name or None,
            }
    return features


# ---------------------------------------------------------------------------
# Scope filter
# ---------------------------------------------------------------------------


def _build_lsd_scope(
    rows_path: Path,
    disease_features: dict[str, dict],
    scope: str,
) -> frozenset[str]:
    """
    Return the set of PrimeKG x_index / y_index values that are within the
    LSD scope. For scope='lsd', keeps nodes within 2 hops of an LSD-seed
    disease. For scope='all', returns an empty set (meaning "all nodes allowed").
    """
    if scope == "all":
        return frozenset()

    # Map MONDO ID -> PrimeKG node indices
    mondo_to_idx: dict[str, str] = {}
    for idx, feat in disease_features.items():
        m = feat.get("mondo_id", "")
        if m:
            # Normalize: MONDO:0018982 or 0018982 -> canonical
            if not m.startswith("MONDO:"):
                m = f"MONDO:{m}"
            mondo_to_idx[m.upper()] = idx

    # Seed node indices (diseases that match LSD_MONDO_SEEDS)
    seed_indices: set[str] = set()
    for mondo_id in LSD_MONDO_SEEDS:
        idx = mondo_to_idx.get(mondo_id.upper())
        if idx:
            seed_indices.add(idx)
        # Also try partial match (some PrimeKG entries strip MONDO: prefix)
        bare = mondo_id.replace("MONDO:", "")
        for stored_mondo, stored_idx in mondo_to_idx.items():
            if bare in stored_mondo:
                seed_indices.add(stored_idx)

    if not seed_indices:
        _log.warning(
            "primekg.scope_filter.no_seeds_matched",
            n_disease_features=len(disease_features),
            hint="Check disease_features.csv column names",
        )
        return frozenset()  # fall back to all-pass

    _log.info("primekg.scope_filter.seeds", n_seeds=len(seed_indices))

    # BFS up to k=1 hop in the edge list to find connected nodes
    # (we use k=1 to keep the set tractable for the first pass;
    #  the KG service itself does k=2 for the frontend).
    hop1: set[str] = set(seed_indices)
    edges_scanned = 0
    # First pass: collect all 1-hop neighbours
    with open(rows_path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            xi = row.get("x_index", "")
            yi = row.get("y_index", "")
            edges_scanned += 1
            if xi in seed_indices or yi in seed_indices:
                hop1.add(xi)
                hop1.add(yi)

    _log.info(
        "primekg.scope_filter.done",
        n_seeds=len(seed_indices),
        n_hop1=len(hop1),
        edges_scanned=edges_scanned,
    )
    return frozenset(hop1)


# ---------------------------------------------------------------------------
# Main ingestor class
# ---------------------------------------------------------------------------


class PrimeKGIngestor(Ingestor):
    name = "primekg"
    priority = 5

    def required_files(self, settings: Settings) -> list[Path]:
        raw = settings.raw_dir / "primekg"
        return [raw / "kg.csv"]  # feature CSVs are optional but nice

    def run(self, settings: Settings) -> IngestionOutput:
        self.check_required_files(settings)

        raw = settings.raw_dir / "primekg"
        kg_path = raw / "kg.csv"
        disease_feat_path = raw / "disease_features.csv"
        drug_feat_path = raw / "drug_features.csv"

        _log.info("primekg.load_features")
        disease_features = _load_disease_features(disease_feat_path)
        drug_features = _load_drug_features(drug_feat_path)
        _log.info(
            "primekg.features_loaded",
            n_disease=len(disease_features),
            n_drug=len(drug_features),
        )

        scope = settings.DISEASE_SCOPE
        if scope != "all":
            _log.info("primekg.building_scope_filter", scope=scope)
            allowed_indices = _build_lsd_scope(kg_path, disease_features, scope)
            _log.info("primekg.scope_size", n_allowed=len(allowed_indices))
        else:
            allowed_indices = frozenset()  # all pass

        acc = KGAccumulator()
        n_rows = 0
        n_skipped_type = 0
        n_skipped_scope = 0
        n_skipped_rel = 0

        _log.info("primekg.ingesting", kg=str(kg_path))

        # Build enriched node data from feature files
        dis_feat_by_idx = disease_features  # {node_index: {mondo_id, omim_id, ...}}
        drug_feat_by_idx = drug_features

        with open(kg_path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                n_rows += 1
                if n_rows % 500_000 == 0:
                    _log.info(
                        "primekg.progress",
                        rows=n_rows,
                        nodes=acc.n_nodes,
                        edges=acc.n_edges,
                    )

                rel_type = row.get("relation_type", "").strip()
                x_index = row.get("x_index", "").strip()
                y_index = row.get("y_index", "").strip()
                x_type_raw = row.get("x_type", "").strip()
                y_type_raw = row.get("y_type", "").strip()
                x_id = row.get("x_id", "").strip()
                y_id = row.get("y_id", "").strip()
                x_name = row.get("x_name", "").strip()
                y_name = row.get("y_name", "").strip()
                x_source = row.get("x_source", "").strip()
                y_source = row.get("y_source", "").strip()

                # Scope filter
                if allowed_indices and x_index not in allowed_indices and y_index not in allowed_indices:
                    n_skipped_scope += 1
                    continue

                # Check relation
                rel_info = _REL_MAP.get(rel_type)
                if rel_info is None:
                    n_skipped_rel += 1
                    continue

                canonical_rel, do_reverse = rel_info

                # Build nodes
                x_node_type = _NODE_TYPE_MAP.get(x_type_raw.lower().strip())
                y_node_type = _NODE_TYPE_MAP.get(y_type_raw.lower().strip())

                if x_node_type is None or y_node_type is None:
                    n_skipped_type += 1
                    continue

                x_cid = _node_canonical_id(x_type_raw, x_source, x_id)
                y_cid = _node_canonical_id(y_type_raw, y_source, y_id)
                if not x_cid or not y_cid:
                    n_skipped_type += 1
                    continue

                # Build node dicts with xrefs
                x_xrefs: dict[str, str] = {}
                y_xrefs: dict[str, str] = {}
                ns_x = _source_ns(x_source)
                ns_y = _source_ns(y_source)
                if x_id and ns_x != "ext_id":
                    x_xrefs[ns_x] = x_id
                if y_id and ns_y != "ext_id":
                    y_xrefs[ns_y] = y_id

                # Enrich with feature CSVs
                if x_node_type == "Disease" and x_index in dis_feat_by_idx:
                    feat = dis_feat_by_idx[x_index]
                    for k in ("mondo_id", "omim_id", "doid_id"):
                        v = feat.get(k)
                        if v:
                            x_xrefs.setdefault(k, v)
                    if feat.get("name") and not x_name:
                        x_name = feat["name"]

                if y_node_type == "Disease" and y_index in dis_feat_by_idx:
                    feat = dis_feat_by_idx[y_index]
                    for k in ("mondo_id", "omim_id", "doid_id"):
                        v = feat.get(k)
                        if v:
                            y_xrefs.setdefault(k, v)
                    if feat.get("name") and not y_name:
                        y_name = feat["name"]

                if x_node_type == "Drug" and x_index in drug_feat_by_idx:
                    feat = drug_feat_by_idx[x_index]
                    for k in ("drugbank_id", "pubchem_cid", "chembl_id"):
                        v = feat.get(k)
                        if v:
                            x_xrefs.setdefault(k, v)

                if y_node_type == "Drug" and y_index in drug_feat_by_idx:
                    feat = drug_feat_by_idx[y_index]
                    for k in ("drugbank_id", "pubchem_cid", "chembl_id"):
                        v = feat.get(k)
                        if v:
                            y_xrefs.setdefault(k, v)

                acc.add_node(
                    {"id": x_cid, "name": x_name, "type": x_node_type, "xrefs": x_xrefs}
                )
                acc.add_node(
                    {"id": y_cid, "name": y_name, "type": y_node_type, "xrefs": y_xrefs}
                )

                # Build edge
                head_cid, tail_cid = (y_cid, x_cid) if do_reverse else (x_cid, y_cid)
                edge: dict = {
                    "head": head_cid,
                    "rel": canonical_rel,
                    "tail": tail_cid,
                    "source": "primekg",
                }
                # TREATS from PrimeKG lacks approval_year — DrugCentral will overwrite
                acc.add_edge(edge, priority=self.priority)

        _log.info(
            "primekg.done",
            rows_total=n_rows,
            skipped_scope=n_skipped_scope,
            skipped_type=n_skipped_type,
            skipped_rel=n_skipped_rel,
            n_nodes=acc.n_nodes,
            n_edges=acc.n_edges,
        )

        stats = IngestorStats(
            n_nodes_added=acc.n_nodes,
            n_edges_added=acc.n_edges,
            source=self.name,
        )
        out = acc.to_output()
        result = IngestionOutput(nodes=out["nodes"], edges=out["edges"], stats=stats)
        self.save_checkpoint(
            settings, n_nodes=acc.n_nodes, n_edges=acc.n_edges, kg_rows=n_rows
        )
        return result


if __name__ == "__main__":
    from app.core.config import get_settings

    settings = get_settings()
    ingestor = PrimeKGIngestor()
    out = ingestor.run(settings)
    print(f"PrimeKG: {len(out.nodes)} nodes, {len(out.edges)} edges")

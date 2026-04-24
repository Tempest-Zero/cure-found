"""
HPO ingestor.

Sources
-------
data/raw/hpo/hp.obo
    Human Phenotype Ontology OBO file. We parse:
    - Symptom node for each [Term] block with id HP:...
    - Synonym names stored in the node's `synonyms` field (used by /search)
    - is_a relationships NOT stored as edges (the phenotype DAG is not currently
      in our canonical relation vocab; it's used for Resnik similarity in Phase 4).

data/raw/hpo/phenotype.hpoa
    OMIM / ORPHA disease -> HPO phenotype annotations.
    Columns: DatabaseID, DiseaseName, Qualifier, HPO_ID, Reference,
             Evidence, Onset, Frequency, Sex, Modifier, Aspect, Biocuration
    We emit Disease HAS_PHENOTYPE Symptom edges for all rows where
    Qualifier != "NOT" (negative annotations excluded).

data/raw/hpo/genes_to_phenotype.txt   (optional)
    gene_id \t gene_symbol \t HPO_ID \t HPO_label \t ...
    We emit Gene HAS_PHENOTYPE Symptom edges.

Priority: 7 (beats PrimeKG=5; loses to DrugCentral=10 for TREATS).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.etl._base import IngestionOutput, Ingestor, IngestorStats, KGAccumulator

if TYPE_CHECKING:
    from app.core.config import Settings

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# OBO parser (minimal, handles hp.obo)
# ---------------------------------------------------------------------------


def _parse_hpo_obo(path: Path) -> list[dict]:
    """Parse hp.obo, returning a list of HPO term dicts:
    {id, name, synonyms, definition, is_obsolete, alt_ids}."""
    terms: list[dict] = []
    current: dict | None = None

    with open(path, encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if line == "[Term]":
                if current:
                    terms.append(current)
                current = {"synonyms": [], "alt_ids": [], "is_a": [], "is_obsolete": False}
                continue
            if not current:
                continue
            if line.startswith("id: "):
                current["id"] = line[4:].strip()
            elif line.startswith("name: "):
                current["name"] = line[6:].strip()
            elif line.startswith("def: "):
                # def: "text" [PMID:...]
                m = re.match(r'def:\s+"([^"]+)"', line)
                if m:
                    current["definition"] = m.group(1)
            elif line.startswith("synonym: "):
                # synonym: "text" EXACT [HPO:curators]
                m = re.match(r'synonym:\s+"([^"]+)"', line)
                if m:
                    current["synonyms"].append(m.group(1))
            elif line.startswith("alt_id: "):
                current["alt_ids"].append(line[8:].strip())
            elif line.startswith("is_a: "):
                # is_a: HP:0000001 ! All
                parent_id = line[6:].split("!")[0].strip()
                current["is_a"].append(parent_id)
            elif line.startswith("is_obsolete: true"):
                current["is_obsolete"] = True

    if current:
        terms.append(current)
    return terms


def _hpo_canonical_id(hpo_id: str) -> str:
    """HP:0001250 -> S:HP_0001250"""
    return "S:" + hpo_id.replace(":", "_")


# ---------------------------------------------------------------------------
# Disease ID from HPOA DatabaseID
# ---------------------------------------------------------------------------


def _disease_cid_from_hpoa(db_id: str) -> str | None:
    """OMIM:123456 -> D:OMIM_123456, ORPHA:586 -> D:ORPHA_586."""
    if not db_id:
        return None
    db_id = db_id.strip()
    if db_id.startswith("OMIM:"):
        return f"D:OMIM_{db_id[5:]}"
    if db_id.startswith("ORPHA:"):
        return f"D:ORPHA_{db_id[6:]}"
    if db_id.startswith("DECIPHER:"):
        return f"D:DECIPHER_{db_id[9:]}"
    return None


# ---------------------------------------------------------------------------
# Ingestor class
# ---------------------------------------------------------------------------


class HPOIngestor(Ingestor):
    name = "hpo"
    priority = 7

    def required_files(self, settings: Settings) -> list[Path]:
        raw = settings.raw_dir / "hpo"
        return [raw / "hp.obo", raw / "phenotype.hpoa"]

    def run(self, settings: Settings) -> IngestionOutput:
        self.check_required_files(settings)
        raw = settings.raw_dir / "hpo"
        obo_path = raw / "hp.obo"
        hpoa_path = raw / "phenotype.hpoa"
        g2p_path = raw / "genes_to_phenotype.txt"

        # ---- 1. Parse OBO -> Symptom nodes ---- #
        _log.info("hpo.parse_obo", path=str(obo_path))
        terms = _parse_hpo_obo(obo_path)
        _log.info("hpo.obo_terms", n=len(terms))

        acc = KGAccumulator()
        n_symptoms = 0
        n_obsolete = 0

        # hpo_id -> canonical id map (for resolving HPOA)
        hpo_to_cid: dict[str, str] = {}

        for term in terms:
            hpo_id = term.get("id", "")
            if not hpo_id.startswith("HP:"):
                continue
            if term.get("is_obsolete"):
                n_obsolete += 1
                continue
            name = term.get("name", "")
            if not name:
                continue
            cid = _hpo_canonical_id(hpo_id)
            hpo_to_cid[hpo_id.upper()] = cid
            # Alt IDs also resolve to the same canonical id
            for alt in term.get("alt_ids", []):
                hpo_to_cid[alt.upper()] = cid

            node: dict = {
                "id": cid,
                "name": name,
                "type": "Symptom",
                "xrefs": {"hpo_id": hpo_id},
            }
            if term.get("synonyms"):
                node["synonyms"] = term["synonyms"]
            acc.add_node(node)
            n_symptoms += 1

        _log.info("hpo.symptoms_added", n=n_symptoms, n_obsolete=n_obsolete)

        # ---- 2. Parse HPOA -> Disease HAS_PHENOTYPE Symptom edges ---- #
        _log.info("hpo.parse_hpoa", path=str(hpoa_path))
        n_edges = 0
        n_neg = 0
        n_no_disease = 0

        with open(hpoa_path, encoding="utf-8", newline="") as fh:
            # Skip comment lines starting with #
            lines = (line for line in fh if not line.startswith("#"))
            reader = csv.DictReader(lines, delimiter="\t")
            for row in reader:
                db_id = row.get("database_id", "") or row.get("DatabaseID", "")
                qualifier = (row.get("qualifier", "") or row.get("Qualifier", "")).strip().upper()
                hpo_id = (row.get("hpo_id", "") or row.get("HPO_ID", "")).strip()
                disease_name = (
                    row.get("disease_name", "")
                    or row.get("DiseaseName", "")
                    or ""
                ).strip()

                # Skip negative annotations
                if qualifier == "NOT":
                    n_neg += 1
                    continue

                d_cid = _disease_cid_from_hpoa(db_id)
                if not d_cid:
                    n_no_disease += 1
                    continue

                s_cid = hpo_to_cid.get(hpo_id.upper())
                if not s_cid:
                    # Symptom might be in a sub-ontology not in our scope; skip
                    continue

                acc.add_node(
                    {
                        "id": d_cid,
                        "name": disease_name,
                        "type": "Disease",
                        "xrefs": self._dis_xrefs(db_id),
                    }
                )
                acc.add_edge(
                    {
                        "head": d_cid,
                        "rel": "HAS_PHENOTYPE",
                        "tail": s_cid,
                        "source": "hpo",
                    },
                    priority=self.priority,
                )
                n_edges += 1

        _log.info(
            "hpo.hpoa_done",
            n_edges=n_edges,
            n_neg_skipped=n_neg,
            n_no_disease_skipped=n_no_disease,
        )

        # ---- 3. Optional: genes_to_phenotype ---- #
        n_gene_edges = 0
        if g2p_path.exists():
            _log.info("hpo.parse_genes_to_phenotype", path=str(g2p_path))
            with open(g2p_path, encoding="utf-8", newline="") as fh:
                lines_g = (line for line in fh if not line.startswith("#"))
                reader_g = csv.DictReader(lines_g, delimiter="\t")
                for row in reader_g:
                    gene_id = (row.get("gene_id", "") or row.get("ncbi_gene_id", "")).strip()
                    gene_sym = (row.get("gene_symbol", "") or "").strip()
                    hpo_id = (row.get("hpo_id", "") or row.get("HPO_ID", "")).strip()

                    if not (gene_id and hpo_id):
                        continue

                    g_cid = f"G:NCBI_{gene_id}"
                    s_cid = hpo_to_cid.get(hpo_id.upper())
                    if not s_cid:
                        continue

                    acc.add_node(
                        {"id": g_cid, "name": gene_sym, "type": "Gene",
                         "xrefs": {"ncbi_gene_id": gene_id}}
                    )
                    acc.add_edge(
                        {"head": g_cid, "rel": "HAS_PHENOTYPE", "tail": s_cid, "source": "hpo"},
                        priority=self.priority,
                    )
                    n_gene_edges += 1

            _log.info("hpo.gene_phenotype_edges", n=n_gene_edges)

        stats = IngestorStats(
            n_nodes_added=acc.n_nodes,
            n_edges_added=acc.n_edges,
            source=self.name,
        )
        out = acc.to_output()
        result = IngestionOutput(nodes=out["nodes"], edges=out["edges"], stats=stats)
        self.save_checkpoint(
            settings, n_symptoms=n_symptoms, n_disease_pheno_edges=n_edges
        )
        return result

    @staticmethod
    def _dis_xrefs(db_id: str) -> dict[str, str]:
        if db_id.startswith("OMIM:"):
            return {"omim_id": db_id[5:]}
        if db_id.startswith("ORPHA:"):
            return {"orpha_id": db_id[6:]}
        return {}


if __name__ == "__main__":
    from app.core.config import get_settings

    settings = get_settings()
    out = HPOIngestor().run(settings)
    print(f"HPO: {len(out.nodes)} nodes, {len(out.edges)} edges")

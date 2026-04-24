"""
Reactome ingestor.

Files consumed
--------------
data/raw/reactome/ReactomePathways.txt
    Tab-separated: pathway_id \t pathway_name \t species
    e.g. R-HSA-109581 \t Apoptosis \t Homo sapiens
    We keep only human (Homo sapiens) pathways.

data/raw/reactome/NCBI2Reactome.txt
    Tab-separated: ncbi_gene_id \t pathway_id \t url \t pathway_name \t evidence \t species
    Gene -> Pathway (PARTICIPATES_IN). Human only.

data/raw/reactome/UniProt2Reactome.txt
    Tab-separated: uniprot_id \t pathway_id \t url \t pathway_name \t evidence \t species
    Protein -> Pathway (PARTICIPATES_IN). Human only.

data/raw/reactome/ReactomePathwaysRelation.txt
    Tab-separated: parent_id \t child_id
    Pathway hierarchy. Currently NOT emitted as edges (not in canonical vocab).
    Useful for future Phase 4 pathway-level Resnik similarity.

What this ingestor emits
------------------------
- Pathway nodes (PW:R_HSA_<suffix>)
- Gene PARTICIPATES_IN Pathway edges (from NCBI2Reactome)
- Protein PARTICIPATES_IN Pathway edges (from UniProt2Reactome)

Priority: 6 (same as Orphanet; above PrimeKG=5).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.etl._base import IngestionOutput, Ingestor, IngestorStats, KGAccumulator

if TYPE_CHECKING:
    from app.core.config import Settings

_log = get_logger(__name__)

_HUMAN_SPECIES = {"homo sapiens", "hsa"}


def _pathway_cid(reactome_id: str) -> str:
    """R-HSA-109581 -> PW:R_HSA_109581"""
    return "PW:" + reactome_id.replace("-", "_")


class ReactomeIngestor(Ingestor):
    name = "reactome"
    priority = 6

    def required_files(self, settings: Settings) -> list[Path]:
        raw = settings.raw_dir / "reactome"
        return [
            raw / "ReactomePathways.txt",
            raw / "NCBI2Reactome.txt",
        ]

    def run(self, settings: Settings) -> IngestionOutput:
        self.check_required_files(settings)
        raw = settings.raw_dir / "reactome"

        pathways_path = raw / "ReactomePathways.txt"
        ncbi_path = raw / "NCBI2Reactome.txt"
        uniprot_path = raw / "UniProt2Reactome.txt"  # optional

        # ---- 1. Parse pathway list ---- #
        _log.info("reactome.parse_pathways", path=str(pathways_path))
        acc = KGAccumulator()
        human_pathway_ids: set[str] = set()

        with open(pathways_path, encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter="\t")
            for row in reader:
                if len(row) < 3:
                    continue
                pw_id, pw_name, species = row[0].strip(), row[1].strip(), row[2].strip()
                if species.lower() not in _HUMAN_SPECIES:
                    continue
                cid = _pathway_cid(pw_id)
                acc.add_node(
                    {
                        "id": cid,
                        "name": pw_name,
                        "type": "Pathway",
                        "xrefs": {"reactome_id": pw_id},
                    }
                )
                human_pathway_ids.add(pw_id)

        _log.info("reactome.pathways", n=len(human_pathway_ids))

        # ---- 2. NCBI gene -> pathway ---- #
        n_gene_edges = 0
        _log.info("reactome.parse_ncbi2reactome", path=str(ncbi_path))
        with open(ncbi_path, encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter="\t")
            for row in reader:
                # Columns: gene_id, pw_id, url, pw_name, evidence, species
                if len(row) < 6:
                    continue
                gene_id, pw_id = row[0].strip(), row[1].strip()
                species = row[5].strip()
                if species.lower() not in _HUMAN_SPECIES:
                    continue
                if pw_id not in human_pathway_ids:
                    continue
                g_cid = f"G:NCBI_{gene_id}"
                pw_cid = _pathway_cid(pw_id)
                acc.add_node(
                    {"id": g_cid, "name": f"NCBI:{gene_id}", "type": "Gene",
                     "xrefs": {"ncbi_gene_id": gene_id}}
                )
                acc.add_edge(
                    {"head": g_cid, "rel": "PARTICIPATES_IN", "tail": pw_cid, "source": "reactome"},
                    priority=self.priority,
                )
                n_gene_edges += 1

        _log.info("reactome.ncbi_edges", n=n_gene_edges)

        # ---- 3. UniProt protein -> pathway (optional) ---- #
        n_prot_edges = 0
        if uniprot_path.exists():
            _log.info("reactome.parse_uniprot2reactome", path=str(uniprot_path))
            with open(uniprot_path, encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh, delimiter="\t")
                for row in reader:
                    if len(row) < 6:
                        continue
                    prot_id, pw_id = row[0].strip(), row[1].strip()
                    species = row[5].strip()
                    if species.lower() not in _HUMAN_SPECIES:
                        continue
                    if pw_id not in human_pathway_ids:
                        continue
                    p_cid = f"P:{prot_id.upper()}"
                    pw_cid = _pathway_cid(pw_id)
                    acc.add_node(
                        {"id": p_cid, "name": prot_id, "type": "Protein",
                         "xrefs": {"uniprot_id": prot_id}}
                    )
                    acc.add_edge(
                        {"head": p_cid, "rel": "PARTICIPATES_IN", "tail": pw_cid,
                         "source": "reactome"},
                        priority=self.priority,
                    )
                    n_prot_edges += 1
            _log.info("reactome.uniprot_edges", n=n_prot_edges)

        _log.info(
            "reactome.done",
            n_nodes=acc.n_nodes,
            n_gene_edges=n_gene_edges,
            n_prot_edges=n_prot_edges,
        )

        out = acc.to_output()
        stats = IngestorStats(
            n_nodes_added=acc.n_nodes,
            n_edges_added=acc.n_edges,
            source=self.name,
        )
        result = IngestionOutput(nodes=out["nodes"], edges=out["edges"], stats=stats)
        self.save_checkpoint(
            settings,
            n_pathways=len(human_pathway_ids),
            n_gene_edges=n_gene_edges,
            n_prot_edges=n_prot_edges,
        )
        return result


if __name__ == "__main__":
    from app.core.config import get_settings

    settings = get_settings()
    out = ReactomeIngestor().run(settings)
    print(f"Reactome: {len(out.nodes)} nodes, {len(out.edges)} edges")

"""
Orphanet ingestor.

Files consumed
--------------
data/raw/orphanet/en_product1.xml
    Disease nomenclature — ORPHA IDs, names, synonyms, OMIM cross-references.
    Freely available from https://www.orphadata.com/data/xml/en_product1.xml

data/raw/orphanet/en_product4.xml   (optional — requires free account)
    Disease-phenotype associations (ORPHA -> HP).
    If absent, we rely on HPOA annotations from the HPO ingestor.

What this ingestor emits
------------------------
- Disease nodes enriched with ORPHA IDs and OMIM cross-references.
- HAS_PHENOTYPE edges if en_product4.xml is present.
- `is_rare=true` flag on all Disease nodes (all Orphanet diseases are rare).

Priority: 6 (above PrimeKG=5; HPO=7 wins for phenotype edges).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.etl._base import IngestionOutput, Ingestor, IngestorStats, KGAccumulator

if TYPE_CHECKING:
    from app.core.config import Settings

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# XML parsers
# ---------------------------------------------------------------------------


def _parse_product1(path: Path) -> list[dict]:
    """Parse en_product1.xml, return list of disease dicts."""
    _log.info("orphanet.parse_product1", path=str(path))
    tree = ET.parse(path)
    root = tree.getroot()

    diseases: list[dict] = []

    # XPath pattern varies slightly between Orphanet XML releases.
    # Try two common root structures:
    disorder_list = root.find(".//DisorderList")
    if disorder_list is None:
        disorder_list = root

    for disorder in (disorder_list or root).iter("Disorder"):
        orpha_code_el = disorder.find("OrphaCode")
        name_el = disorder.find("Name")
        if orpha_code_el is None or name_el is None:
            continue

        orpha_id = f"ORPHA:{orpha_code_el.text}"
        name = name_el.text or ""

        # Synonyms
        synonyms: list[str] = []
        for syn in disorder.findall(".//SynonymList/Synonym"):
            if syn.text:
                synonyms.append(syn.text)

        # External references (OMIM, UMLS, MeSH, etc.)
        omim_ids: list[str] = []
        for ext_ref in disorder.findall(".//ExternalReferenceList/ExternalReference"):
            source_el = ext_ref.find("Source")
            ref_el = ext_ref.find("Reference")
            if source_el is not None and ref_el is not None:
                src = (source_el.text or "").strip().upper()
                ref = (ref_el.text or "").strip()
                if src == "OMIM" and ref:
                    omim_ids.append(ref)

        diseases.append(
            {
                "orpha_id": orpha_id,
                "name": name,
                "synonyms": synonyms,
                "omim_ids": omim_ids,
            }
        )

    _log.info("orphanet.product1_diseases", n=len(diseases))
    return diseases


def _parse_product4(path: Path) -> list[tuple[str, str, str]]:
    """Parse en_product4.xml, return list of (orpha_id, hpo_id, frequency)."""
    if not path.exists():
        return []
    _log.info("orphanet.parse_product4", path=str(path))
    tree = ET.parse(path)
    root = tree.getroot()
    assocs: list[tuple[str, str, str]] = []

    for disorder in root.iter("Disorder"):
        orpha_el = disorder.find("OrphaCode")
        if orpha_el is None:
            continue
        orpha_id = f"ORPHA:{orpha_el.text}"

        for pheno_assoc in disorder.findall(".//HPODisorderAssociationList/HPODisorderAssociation"):
            hpo_id_el = pheno_assoc.find("HPO/HPOId")
            freq_el = pheno_assoc.find("HPOFrequency/Name")
            if hpo_id_el is not None and hpo_id_el.text:
                freq = freq_el.text if freq_el is not None else ""
                assocs.append((orpha_id, hpo_id_el.text.strip(), freq or ""))

    _log.info("orphanet.product4_assocs", n=len(assocs))
    return assocs


# ---------------------------------------------------------------------------
# Ingestor class
# ---------------------------------------------------------------------------


class OrphanetIngestor(Ingestor):
    name = "orphanet"
    priority = 6

    def required_files(self, settings: Settings) -> list[Path]:
        raw = settings.raw_dir / "orphanet"
        return [raw / "en_product1.xml"]

    def run(self, settings: Settings) -> IngestionOutput:
        self.check_required_files(settings)
        raw = settings.raw_dir / "orphanet"

        product1_path = raw / "en_product1.xml"
        product4_path = raw / "en_product4.xml"  # optional

        diseases = _parse_product1(product1_path)
        pheno_assocs = _parse_product4(product4_path)

        acc = KGAccumulator()

        # Build HPO canonical id map (needed for product4 edges)
        # S:HP_0001250 <- HP:0001250
        def hpo_to_cid(hpo_id: str) -> str:
            return "S:" + hpo_id.replace(":", "_")

        for d in diseases:
            orpha_id = d["orpha_id"]  # e.g. "ORPHA:77"
            cid = f"D:{orpha_id.replace(':', '_')}"  # D:ORPHA_77

            xrefs: dict[str, str] = {"orpha_id": orpha_id}
            if d["omim_ids"]:
                xrefs["omim_id"] = d["omim_ids"][0]

            node: dict = {
                "id": cid,
                "name": d["name"],
                "type": "Disease",
                "is_rare": True,
                "xrefs": xrefs,
            }
            if d["synonyms"]:
                node["synonyms"] = d["synonyms"]
            acc.add_node(node)

        # Product 4 phenotype edges (only if file is available)
        n_pheno = 0
        for orpha_id, hpo_id, freq in pheno_assocs:
            d_cid = f"D:{orpha_id.replace(':', '_')}"
            s_cid = hpo_to_cid(hpo_id)
            edge: dict = {
                "head": d_cid,
                "rel": "HAS_PHENOTYPE",
                "tail": s_cid,
                "source": "orphanet",
            }
            if freq:
                edge["frequency"] = freq
            acc.add_edge(edge, priority=self.priority)
            n_pheno += 1

        _log.info(
            "orphanet.done",
            n_diseases=acc.n_nodes,
            n_pheno_edges=n_pheno,
        )

        out = acc.to_output()
        stats = IngestorStats(
            n_nodes_added=acc.n_nodes,
            n_edges_added=acc.n_edges,
            source=self.name,
        )
        result = IngestionOutput(nodes=out["nodes"], edges=out["edges"], stats=stats)
        self.save_checkpoint(settings, n_diseases=acc.n_nodes, n_pheno=n_pheno)
        return result


if __name__ == "__main__":
    from app.core.config import get_settings

    settings = get_settings()
    out = OrphanetIngestor().run(settings)
    print(f"Orphanet: {len(out.nodes)} nodes, {len(out.edges)} edges")

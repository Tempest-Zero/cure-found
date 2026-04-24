"""
DrugCentral ingestor.

DrugCentral (https://drugcentral.org) is the authoritative source for
FDA-approved drug-disease TREATS edges with `approval_year`. This ingestor
is designed to run AFTER PrimeKG so its TREATS edges overwrite PrimeKG's
lower-priority entries (DrugCentral priority=10 > PrimeKG priority=5).

Files consumed
--------------
  data/raw/drugcentral/drug_indications.csv
    Columns (may vary by release year):
      struct_id, drug_name, drug_name_preferred, omim_id, do_id, snomed_id,
      concept_name, umls_cui, cui_semantic_type, relationship_name,
      ndcproduct_code, newapproval, source, highest_phase
    Key columns we use: drug_name, omim_id (or do_id), relationship_name,
                        newapproval (approval year)

  data/raw/drugcentral/structures.smiles.csv   (optional)
    Columns: struct_id, inchikey, name, cas_rn, drugbank_id, ...
    Provides DrugBank ID cross-references for drugs.

  data/raw/drugcentral/approval.csv   (optional)
    Columns: struct_id, approval, type, applicant, ...
    Provides per-drug first US approval year.

Output
------
- Drug nodes (DR:<SLUG>, xrefs: drugcentral_id, drugbank_id if available)
- Disease nodes (D:OMIM_<ID>, xrefs: omim_id / mondo_id where we can)
- TREATS edges with approval_year (integer)
- CONTRAINDICATED_FOR edges where relationship_name indicates contraindication

Notes
-----
- We map diseases primarily by OMIM ID. The id_map_service later resolves
  OMIM -> MONDO where the mapping exists.
- When omim_id is null we skip the indication (cannot link to our Disease nodes
  without a resolvable ID).
- `newapproval` may be a year (e.g. "1995") or empty. We default to NULL and
  the eval code handles NULL approval years gracefully.
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

# Relationship names that map to TREATS
_TREATS_NAMES = frozenset(
    {
        "indication",
        "approved_indication",
        "treatment",
        "reduces",
        "prevents",
        "off-label",
        "established_pharmacologic_class",
    }
)

_CONTRA_NAMES = frozenset(
    {
        "contraindication",
        "black_box_warning",
    }
)

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _extract_year(raw: str) -> int | None:
    """Parse an approval year from a DrugCentral date/year field."""
    if not raw:
        return None
    m = _YEAR_RE.search(raw)
    return int(m.group()) if m else None


def _drug_cid(drug_name: str, struct_id: str = "") -> str:
    slug = re.sub(r"[^A-Z0-9]", "_", drug_name.upper().strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return f"DR:DC_{slug}" if slug else f"DR:DC_{struct_id}"


def _disease_cid(omim_id: str = "", do_id: str = "") -> str | None:
    if omim_id and omim_id.strip():
        oid = omim_id.strip().lstrip("0")
        return f"D:OMIM_{oid}"
    if do_id and do_id.strip():
        return f"D:DOID_{do_id.strip().replace(':', '_')}"
    return None


class DrugCentralIngestor(Ingestor):
    name = "drugcentral"
    priority = 10  # beats PrimeKG (5) for TREATS edges

    def required_files(self, settings: Settings) -> list[Path]:
        raw = settings.raw_dir / "drugcentral"
        return [raw / "drug_indications.csv"]

    def run(self, settings: Settings) -> IngestionOutput:
        self.check_required_files(settings)
        raw = settings.raw_dir / "drugcentral"

        # Optional: structures CSV (gives drugbank_id xref)
        struct_path = raw / "structures.smiles.csv"
        approval_path = raw / "approval.csv"

        # Build struct_id -> drugbank_id map from structures CSV
        struct_to_db: dict[str, str] = {}
        if struct_path.exists():
            with open(struct_path, encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    sid = row.get("struct_id", "").strip()
                    db = row.get("drugbank_id", "").strip()
                    if sid and db:
                        struct_to_db[sid] = db

        # Build struct_id -> first_approval_year from approval CSV
        struct_to_year: dict[str, int] = {}
        if approval_path.exists():
            with open(approval_path, encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    sid = row.get("struct_id", "").strip()
                    yr_raw = (
                        row.get("approval", "")
                        or row.get("approval_year", "")
                        or ""
                    ).strip()
                    yr = _extract_year(yr_raw)
                    if sid and yr:
                        existing = struct_to_year.get(sid)
                        if existing is None or yr < existing:
                            struct_to_year[sid] = yr

        indications_path = raw / "drug_indications.csv"
        acc = KGAccumulator()
        n_treats = 0
        n_contra = 0
        n_skipped = 0

        with open(indications_path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                struct_id = row.get("struct_id", "").strip()
                drug_name = (
                    row.get("drug_name_preferred", "")
                    or row.get("drug_name", "")
                    or ""
                ).strip()
                omim_id = row.get("omim_id", "").strip()
                do_id = row.get("do_id", "").strip()
                rel_name = row.get("relationship_name", "").strip().lower()
                yr_raw = (
                    row.get("newapproval", "")
                    or row.get("approval_year", "")
                    or ""
                ).strip()
                disease_name = (
                    row.get("concept_name", "")
                    or row.get("disease_name", "")
                    or ""
                ).strip()

                if not drug_name:
                    n_skipped += 1
                    continue

                d_cid = _disease_cid(omim_id, do_id)
                if not d_cid:
                    n_skipped += 1
                    continue

                drug_cid = _drug_cid(drug_name, struct_id)

                # Determine approval year: prefer approval.csv, then inline
                yr = struct_to_year.get(struct_id) or _extract_year(yr_raw)

                # Node xrefs
                drug_xrefs: dict[str, str] = {}
                if struct_id:
                    drug_xrefs["drugcentral_id"] = struct_id
                db_id = struct_to_db.get(struct_id, "")
                if db_id:
                    drug_xrefs["drugbank_id"] = db_id

                dis_xrefs: dict[str, str] = {}
                if omim_id:
                    dis_xrefs["omim_id"] = omim_id
                if do_id:
                    dis_xrefs["doid_id"] = do_id

                acc.add_node({"id": drug_cid, "name": drug_name, "type": "Drug", "xrefs": drug_xrefs})
                acc.add_node(
                    {"id": d_cid, "name": disease_name, "type": "Disease", "xrefs": dis_xrefs}
                )

                if rel_name in _TREATS_NAMES or not rel_name:
                    edge: dict = {
                        "head": drug_cid,
                        "rel": "TREATS",
                        "tail": d_cid,
                        "source": "drugcentral",
                    }
                    if yr is not None:
                        edge["approval_year"] = yr
                    acc.add_edge(edge, priority=self.priority)
                    n_treats += 1
                elif rel_name in _CONTRA_NAMES:
                    acc.add_edge(
                        {
                            "head": drug_cid,
                            "rel": "CONTRAINDICATED_FOR",
                            "tail": d_cid,
                            "source": "drugcentral",
                        },
                        priority=self.priority,
                    )
                    n_contra += 1
                else:
                    n_skipped += 1

        _log.info(
            "drugcentral.done",
            n_treats=n_treats,
            n_contra=n_contra,
            n_skipped=n_skipped,
            n_nodes=acc.n_nodes,
        )

        out = acc.to_output()
        stats = IngestorStats(
            n_nodes_added=acc.n_nodes,
            n_edges_added=acc.n_edges,
            source=self.name,
        )
        result = IngestionOutput(nodes=out["nodes"], edges=out["edges"], stats=stats)
        self.save_checkpoint(settings, n_treats=n_treats, n_contra=n_contra)
        return result


if __name__ == "__main__":
    from app.core.config import get_settings

    settings = get_settings()
    out = DrugCentralIngestor().run(settings)
    print(f"DrugCentral: {len(out.nodes)} nodes, {len(out.edges)} edges")

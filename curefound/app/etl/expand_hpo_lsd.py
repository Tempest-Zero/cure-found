"""Expand the seed KG with HPO phenotype.hpoa annotations, scoped to the 13 LSD diseases.

This is a deliberately narrow tool. Unlike `app.etl.ingest.hpo` (which builds
a general-purpose HPO graph with thousands of new nodes), this script:

1. Reads the existing 99-node seed KG.
2. Pulls the official HPO disease-phenotype annotations (`phenotype.hpoa`).
3. Filters to rows whose `database_id` matches one of our 13 LSD diseases via
   OMIM/ORPHA xrefs already on the seed.
4. Adds `HAS_PHENOTYPE` edges to existing diseases. New symptoms encountered
   are added as `S:HP_NNNNNNN` nodes, but the disease vocabulary is frozen.
5. Skips qualifier="NOT" rows and non-P aspects (we only want phenotypic
   abnormality).
6. Writes the expanded KG to `data/seed/kg-expanded.json` so the original
   seed stays as a regression baseline.

Run:
    python -m app.etl.expand_hpo_lsd            # default paths
    python -m app.etl.expand_hpo_lsd --output data/seed/kg-expanded.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SEED_KG = ROOT / "data" / "seed" / "kg.json"
HPOA = ROOT / "data" / "raw" / "hpo" / "phenotype.hpoa"
OUT_DEFAULT = ROOT / "data" / "seed" / "kg-expanded.json"

# Aspect codes from phenotype.hpoa column 11.
# We want only "P" (phenotypic abnormality). Skip:
#   I = inheritance, C = clinical course, M = modifier
INCLUDE_ASPECTS = {"P"}


def _load_seed(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_id_maps(kg: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Build OMIM/ORPHA -> seed disease id, and HP -> seed symptom id."""
    disease_map: dict[str, str] = {}
    symptom_map: dict[str, str] = {}

    for n in kg["nodes"]:
        xr = n.get("xrefs") or {}
        if n["type"] == "Disease":
            if omim := xr.get("omim_id"):
                disease_map[f"OMIM:{omim}"] = n["id"]
            if orpha := xr.get("orpha_id"):
                disease_map[f"ORPHA:{orpha}"] = n["id"]
            if mondo := xr.get("mondo_id"):
                disease_map[mondo] = n["id"]
        elif n["type"] == "Symptom":
            if hp := xr.get("hpo_id"):
                symptom_map[hp] = n["id"]

    return disease_map, symptom_map


def _parse_hpo_obo_names(obo_path: Path) -> dict[str, str]:
    """Build HP id -> term name map from hp.obo (best-effort, no full parser)."""
    if not obo_path.exists():
        return {}
    out: dict[str, str] = {}
    cur_id: str | None = None
    pattern_id = re.compile(r"^id:\s+(HP:\d+)")
    pattern_name = re.compile(r"^name:\s+(.+?)\s*$")
    for raw in obo_path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("[Term]"):
            cur_id = None
            continue
        if m := pattern_id.match(raw):
            cur_id = m.group(1)
            continue
        if cur_id is not None and (m := pattern_name.match(raw)):
            out[cur_id] = m.group(1)
            cur_id = None
    return out


def expand(seed_path: Path, hpoa_path: Path, out_path: Path) -> dict[str, int]:
    kg = _load_seed(seed_path)
    disease_map, symptom_map = _build_id_maps(kg)

    obo_path = hpoa_path.parent / "hp.obo"
    hp_names = _parse_hpo_obo_names(obo_path)
    if hp_names:
        print(f"  loaded {len(hp_names):,} HP term names from hp.obo")

    # Existing edges as a set so we don't double-add.
    edge_keys: set[tuple[str, str, str]] = {(e["head"], e["rel"], e["tail"]) for e in kg["edges"]}
    existing_node_ids: set[str] = {n["id"] for n in kg["nodes"]}

    # Counters
    n_rows_total = 0
    n_rows_lsd = 0
    n_rows_kept = 0
    n_new_edges = 0
    n_new_symptoms = 0
    by_disease: dict[str, int] = defaultdict(int)

    with hpoa_path.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line or line.startswith("#") or line.startswith("database_id"):
                continue
            n_rows_total += 1
            cols = line.split("\t")
            if len(cols) < 11:
                continue

            db_id = cols[0]
            qualifier = cols[2].strip()
            hp_id = cols[3].strip()
            aspect = cols[10].strip()

            if aspect not in INCLUDE_ASPECTS:
                continue
            if qualifier.upper() == "NOT":
                continue

            seed_disease = disease_map.get(db_id)
            if seed_disease is None:
                continue
            n_rows_lsd += 1

            # Resolve symptom — either an existing seed symptom (by HP xref)
            # or create a new node for previously-unseen HP terms.
            seed_symptom = symptom_map.get(hp_id)
            if seed_symptom is None:
                new_id = f"S:HP_{hp_id.split(':')[1]}"
                if new_id not in existing_node_ids:
                    name = hp_names.get(hp_id) or hp_id
                    kg["nodes"].append(
                        {
                            "id": new_id,
                            "type": "Symptom",
                            "name": name,
                            "xrefs": {"hpo_id": hp_id},
                            "source": "hpo_hpoa",
                        }
                    )
                    existing_node_ids.add(new_id)
                    n_new_symptoms += 1
                seed_symptom = new_id
                symptom_map[hp_id] = new_id

            edge_key = (seed_disease, "HAS_PHENOTYPE", seed_symptom)
            if edge_key in edge_keys:
                continue

            kg["edges"].append(
                {
                    "head": seed_disease,
                    "rel": "HAS_PHENOTYPE",
                    "tail": seed_symptom,
                    "source": "hpo_hpoa",
                    "evidence": cols[5] if len(cols) > 5 else "",
                    "frequency": cols[7] if len(cols) > 7 else "",
                }
            )
            edge_keys.add(edge_key)
            n_new_edges += 1
            n_rows_kept += 1
            by_disease[seed_disease] += 1

    # Bump KG version string so anything that pins on it knows the corpus changed.
    kg["kg_version"] = (kg.get("kg_version") or "kg-mvp-0.1") + "+hpo_lsd"
    kg.setdefault("provenance", {}).update(
        {
            "hpo_lsd_expansion": {
                "source": str(hpoa_path.relative_to(ROOT)),
                "rows_total": n_rows_total,
                "rows_lsd_match": n_rows_lsd,
                "edges_added": n_new_edges,
                "new_symptom_nodes": n_new_symptoms,
            }
        }
    )

    out_path.write_text(json.dumps(kg, indent=2), encoding="utf-8")

    return {
        "rows_total": n_rows_total,
        "rows_lsd": n_rows_lsd,
        "rows_kept": n_rows_kept,
        "new_edges": n_new_edges,
        "new_symptoms": n_new_symptoms,
        "n_nodes": len(kg["nodes"]),
        "n_edges": len(kg["edges"]),
        **{f"d_{k}": v for k, v in by_disease.items()},
    }


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="expand_hpo_lsd")
    p.add_argument("--seed", type=Path, default=SEED_KG)
    p.add_argument("--hpoa", type=Path, default=HPOA)
    p.add_argument("--output", type=Path, default=OUT_DEFAULT)
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    if not args.hpoa.exists():
        raise SystemExit(
            f"Missing {args.hpoa}. Run `python -m app.etl.fetch_all --source hpo` first."
        )
    print(f"Reading seed KG: {args.seed}")
    print(f"Reading HPO annotations: {args.hpoa}")
    print(f"Writing expanded KG: {args.output}")
    print()
    stats = expand(args.seed, args.hpoa, args.output)
    print()
    print("=== Expansion summary ===")
    for k, v in stats.items():
        if k.startswith("d_"):
            continue
        print(f"  {k:20s} {v}")
    print()
    print("=== Edges added per disease ===")
    for k, v in sorted(stats.items()):
        if k.startswith("d_"):
            print(f"  {k[2:]:14s} +{v}")


if __name__ == "__main__":
    main()

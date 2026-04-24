"""
Diagnostic / symptom-matching service.

Input:  list of HPO symptom ids (canonical Symptom node ids, e.g. "S:SEIZURES")
        OR raw hpo_id strings (e.g. "HP:0001250") which we canonicalize.
Output: ranked list of candidate diseases with explanations.

Hybrid ranker (matches the plan's Phase 4 design):
  1. Jaccard similarity between input-symptom set and each disease's HPO set.
  2. Inverse-frequency-weighted score (rare symptoms count more -- Resnik-lite).
     The smoothed-IDF formula mirrors sklearn's TfidfVectorizer:
         idf(s) = log((1 + N_diseases) / (1 + df(s))) + 1
     so a symptom shared by every disease gets idf=1 (not 0) and a
     symptom unique to one disease gets the maximum weight.
  3. Reciprocal-rank fusion (k=60) of the two rankings.

Phase 4 swap: replace Jaccard with FAISS-backed cosine over HPO vectors
and add Resnik similarity over the HPO DAG. The `resolve_inputs` /
`predict` interface below is stable.

API contract (fix for C3):
  `resolve_inputs(symptoms) -> (resolved, unresolved)` is a public method.
  Unresolved HPO ids are surfaced to the caller so the UI can flag them
  instead of silently dropping them (as the old `_resolve_input_symptoms`
  did). Input ids are matched case-insensitively against both canonical
  Symptom node ids and the `HP:NNNNNNN` aliases.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from app.kg.loader import KG


@dataclass
class DiagnoseResult:
    disease_id: str
    disease_name: str
    jaccard_score: float
    idf_score: float
    fused_score: float
    matched_symptoms: list[dict]  # [{id, name, hpo_id}]
    missing_symptoms: list[dict]  # symptoms of disease not in input
    is_rare: bool


class DiagnoseService:
    def __init__(self, kg: KG):
        self.kg = kg
        # Disease -> set(symptom_id).
        self.disease_symptoms: dict[str, set[str]] = {}
        for dis in kg.diseases:
            symptoms: set[str] = set()
            for _, s, data in kg.graph.out_edges(dis, data=True):
                if data.get("rel") == "HAS_PHENOTYPE":
                    symptoms.add(s)
            self.disease_symptoms[dis] = symptoms

        # Document frequency of each symptom (how many diseases carry it).
        df: dict[str, int] = {}
        for syms in self.disease_symptoms.values():
            for s in syms:
                df[s] = df.get(s, 0) + 1
        n_diseases = len(self.disease_symptoms) or 1
        # Smoothed IDF (sklearn-style). A symptom shared by every disease gets
        # idf = log((1+N)/(1+N)) + 1 = 1, not 0 -- keeps the score well-defined
        # when overlap is computed against the full set.
        self.idf: dict[str, float] = {
            s: math.log((1 + n_diseases) / (1 + c)) + 1.0 for s, c in df.items()
        }

        # Reverse lookup: hpo_id ("HP:0001250") -> canonical Symptom id
        # ("S:SEIZURES"). Uppercased so matching is case-insensitive.
        self.hpo_to_canonical: dict[str, str] = {}
        for n in kg.node_by_id.values():
            if n["type"] != "Symptom":
                continue
            hpo = (n.get("xrefs") or {}).get("hpo_id")
            if hpo:
                self.hpo_to_canonical[hpo.strip().upper()] = n["id"]

    # ----------------------- input resolution ----------------------- #

    def resolve_inputs(
        self,
        inputs: Iterable[str],
    ) -> tuple[list[str], list[str]]:
        """Split raw input strings into `(resolved, unresolved)`.

          * resolved   canonical Symptom ids, in input order, duplicates
                       collapsed
          * unresolved the original tokens we could not map (for the UI)

        Accepts canonical Symptom ids (`S:SEIZURES`) or HPO ids
        (`HP:0001250`). Case-insensitive on the HPO alias -- the old
        implementation was case-sensitive and quietly dropped
        `hp:0001250` as "unknown", which is the fix for C3.
        """
        resolved: list[str] = []
        unresolved: list[str] = []
        seen: set[str] = set()
        for raw in inputs:
            if raw is None:
                continue
            token = raw.strip()
            if not token:
                continue
            # Exact canonical match first.
            if token in self.kg.node_by_id and self.kg.node_by_id[token]["type"] == "Symptom":
                cid = token
            else:
                cid = self.hpo_to_canonical.get(token.upper())
            if cid is None:
                unresolved.append(token)
                continue
            if cid in seen:
                continue
            seen.add(cid)
            resolved.append(cid)
        return resolved, unresolved

    # ----------------------- ranking ----------------------- #

    def predict(
        self,
        symptom_inputs: Iterable[str],
        top_k: int = 10,
        resolved: list[str] | None = None,
    ) -> list[DiagnoseResult]:
        """Rank diseases by symptom overlap. Callers that have already run
        `resolve_inputs` can pass the result via `resolved` to skip the
        second-pass resolution (fix for C3's double-resolve)."""
        if resolved is None:
            resolved, _ = self.resolve_inputs(symptom_inputs)
        inputs = set(resolved)
        if not inputs:
            return []

        per_disease: list[tuple[str, float, float, set[str]]] = []
        for dis, syms in self.disease_symptoms.items():
            if not syms:
                continue
            overlap = inputs & syms
            union = inputs | syms
            jac = len(overlap) / len(union) if union else 0.0
            idf_score = sum(self.idf.get(s, 0.0) for s in overlap)
            per_disease.append((dis, jac, idf_score, overlap))

        # Tie-break on disease id so ranks are deterministic across runs (H7).
        by_jac = sorted(per_disease, key=lambda x: (-x[1], x[0]))
        by_idf = sorted(per_disease, key=lambda x: (-x[2], x[0]))
        jac_rank = {d: i + 1 for i, (d, *_rest) in enumerate(by_jac)}
        idf_rank = {d: i + 1 for i, (d, *_rest) in enumerate(by_idf)}

        results: list[DiagnoseResult] = []
        for dis, jac, idf, overlap in per_disease:
            rrf = 1.0 / (60 + jac_rank[dis]) + 1.0 / (60 + idf_rank[dis])
            node = self.kg.node_by_id[dis]
            matched = [
                {
                    "id": s,
                    "name": self.kg.node_by_id[s]["name"],
                    "hpo_id": (self.kg.node_by_id[s].get("xrefs") or {}).get("hpo_id"),
                }
                for s in sorted(overlap)
            ]
            missing = [
                {
                    "id": s,
                    "name": self.kg.node_by_id[s]["name"],
                    "hpo_id": (self.kg.node_by_id[s].get("xrefs") or {}).get("hpo_id"),
                }
                for s in sorted(self.disease_symptoms[dis] - overlap)
            ]
            results.append(
                DiagnoseResult(
                    disease_id=dis,
                    disease_name=node["name"],
                    jaccard_score=jac,
                    idf_score=idf,
                    fused_score=rrf,
                    matched_symptoms=matched,
                    missing_symptoms=missing,
                    is_rare=bool(node.get("is_rare", False)),
                )
            )
        results.sort(key=lambda r: (-r.fused_score, r.disease_id))
        return results[:top_k]


def build_default_service() -> DiagnoseService:
    from app.kg.loader import load_kg

    return DiagnoseService(load_kg())


if __name__ == "__main__":
    # Run as a module for correct package resolution:
    #     python -m app.diagnose.service
    svc = build_default_service()

    demos = [
        (
            "Niemann-Pick C profile",
            ["HP:0002240", "HP:0001744", "HP:0000605", "HP:0001251", "HP:0001250", "HP:0001263"],
        ),
        ("Gaucher profile", ["HP:0002240", "HP:0001744", "HP:0001903", "HP:0001873", "HP:0002653"]),
        ("Fabry profile", ["HP:0001073", "HP:0000077", "HP:0009830", "HP:0001638"]),
        (
            "Mystery child (onset infancy, cherry-red, hypotonic)",
            ["HP:0010729", "HP:0001252", "HP:0001263", "HP:0001250"],
        ),
        (
            "Mixed-case + unknown (exercises resolve_inputs)",
            ["hp:0010729", "HP:BOGUS", "S:SEIZURES"],
        ),
    ]
    for name, hpo_ids in demos:
        print(f"\n--- {name} : {hpo_ids} ---")
        resolved, unresolved = svc.resolve_inputs(hpo_ids)
        print(f"  resolved={resolved}  unresolved={unresolved}")
        for r in svc.predict(hpo_ids, top_k=5, resolved=resolved):
            tag = " [rare]" if r.is_rare else ""
            ms = ", ".join(m["name"] for m in r.matched_symptoms[:4])
            print(
                f"  {r.disease_name:32s} jac={r.jaccard_score:.3f}  "
                f"idf={r.idf_score:.2f}  rrf={r.fused_score:.4f}{tag}"
            )
            print(f"    matched: {ms}")

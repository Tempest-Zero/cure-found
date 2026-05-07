"""
Drug-repurposing inference service.

Inputs : disease_id (canonical), top_k, include_already_approved
Outputs: ranked list of drug candidates with:
          - model score (RotatE — relational rotation in complex space)
          - graph evidence score (pathway-overlap Jaccard)
          - fused score (reciprocal-rank fusion, k=60)
          - evidence subgraph (short paths drug -> disease)
          - whether the (drug, disease) edge is already in the KG
            (UI dims "already approved" vs "novel prediction")

Ranking semantics (fix for C4 in the audit plan):
  Approved drugs are filtered OUT of the candidate set BEFORE ranking when
  `include_already_approved=False`. This means:
      - `model_rank` and `graph_rank` are 1..len(candidates), not 1..n_drugs.
      - The rank fields you see on the response match the returned ordering.
  Previously we scored every drug globally, then filtered approved drugs
  post-hoc, which produced nonsense like "position #1 has model_rank=10".

Graph score (fix for H1): the drug-side walker is now explicitly filtered to
`rel == "TARGETS"`. Previously it traversed every out-edge type (including
TREATS), which worked by accident on the seed KG but misfired silently once
heterogeneous edges arrived.

Approval lookup (fix for H2): `kg.treats_edge[(drug, disease)]` is an O(1)
lookup; we no longer scan the full triple list per drug.

Ranking logic is intentionally pluggable -- in Phase 2 the RotatE call gets
replaced by a PyKEEN pipeline (CompGCN, RotatE-MoE, etc.); everything else
stays the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.kg.loader import KG
from app.ml import rotate as kge_mod


@dataclass
class RepurposeResult:
    drug_id: str
    drug_name: str
    model_score: float  # RotatE score (higher = better)
    graph_score: float  # Jaccard over pathway neighborhoods (0..1)
    fused_score: float  # RRF (higher = better)
    model_rank: int  # 1-indexed rank within the candidate set
    graph_rank: int  # 1-indexed rank within the candidate set
    already_approved: bool
    approval_year: int | None
    evidence_paths: list[list[dict[str, Any]]]


class RepurposeService:
    def __init__(self, kg: KG, E: np.ndarray, R: np.ndarray):
        self.kg = kg
        self.E = E
        self.R = R
        # Known TREATS set for "already_approved" flag (fix for H2: read from
        # the KG's pre-built index instead of rebuilding per instance).
        self.treats_set: set[tuple[str, str]] = set(kg.treats_edge.keys())

        # Precompute the set of pathways each drug is connected to via
        # TARGETS -> PARTICIPATES_IN. The explicit rel=="TARGETS" filter is
        # the fix for H1 -- previously the walker traversed every
        # drug-out-edge type.
        self.drug_pathways: dict[str, set[str]] = {}
        for d in kg.drugs:
            pathways: set[str] = set()
            for _, prot, data1 in kg.graph.out_edges(d, data=True):
                if data1.get("rel") != "TARGETS":
                    continue
                for _, pw, data2 in kg.graph.out_edges(prot, data=True):
                    if data2.get("rel") == "PARTICIPATES_IN":
                        pathways.add(pw)
            self.drug_pathways[d] = pathways

        # Precompute pathways each disease is tied to via
        # CAUSES/ASSOCIATED_WITH -> ENCODES -> PARTICIPATES_IN.
        self.disease_pathways: dict[str, set[str]] = {}
        for dis in kg.diseases:
            pathways: set[str] = set()
            for g, _, data1 in kg.graph.in_edges(dis, data=True):
                if data1.get("rel") not in ("CAUSES", "ASSOCIATED_WITH"):
                    continue
                for _, prot, data2 in kg.graph.out_edges(g, data=True):
                    if data2.get("rel") != "ENCODES":
                        continue
                    for _, pw, data3 in kg.graph.out_edges(prot, data=True):
                        if data3.get("rel") == "PARTICIPATES_IN":
                            pathways.add(pw)
            self.disease_pathways[dis] = pathways

    def predict(
        self, disease_id: str, top_k: int = 10, include_already_approved: bool = False
    ) -> list[RepurposeResult]:
        if disease_id not in self.kg.node_by_id:
            raise KeyError(f"Unknown disease id: {disease_id}")

        # ---- 1. Determine the candidate set UP FRONT (fix for C4) ---- #
        if include_already_approved:
            candidates = list(self.kg.drugs)
        else:
            candidates = [d for d in self.kg.drugs if (d, disease_id) not in self.treats_set]
        # Alphabetical order -> deterministic rank assignment in ties (H7).
        candidates.sort()
        if not candidates:
            return []

        cand_idxs = np.array([self.kg.entity_to_idx[d] for d in candidates], dtype=np.int64)

        # ---- 2. Model scores over the candidate set only ---- #
        r_idx = self.kg.relation_to_idx["TREATS"]
        dis_idx = self.kg.entity_to_idx[disease_id]
        ranked_idx, ranked_scores = kge_mod.rank_heads(self.E, self.R, r_idx, dis_idx, cand_idxs)
        model_score_of = {
            self.kg.idx_to_entity[int(e)]: float(s)
            for e, s in zip(ranked_idx, ranked_scores, strict=False)
        }
        # Assign ranks with canonical-id tiebreak (H7).
        model_ranked = sorted(candidates, key=lambda d: (-model_score_of[d], d))
        model_rank_of = {d: i + 1 for i, d in enumerate(model_ranked)}

        # ---- 3. Graph scores over the candidate set only ---- #
        dis_pw = self.disease_pathways.get(disease_id, set())
        graph_score_of: dict[str, float] = {}
        for d in candidates:
            dp = self.drug_pathways.get(d, set())
            if not dp and not dis_pw:
                graph_score_of[d] = 0.0
            else:
                union = len(dp | dis_pw) or 1
                graph_score_of[d] = len(dp & dis_pw) / union

        graph_ranked = sorted(candidates, key=lambda d: (-graph_score_of[d], d))
        graph_rank_of = {d: i + 1 for i, d in enumerate(graph_ranked)}

        # ---- 4. Fuse by RRF (k=60 is standard) ---- #
        def rrf(d: str) -> float:
            return 1.0 / (60 + model_rank_of[d]) + 1.0 / (60 + graph_rank_of[d])

        fused_order = sorted(candidates, key=lambda d: (-rrf(d), d))
        top = fused_order[:top_k]

        # ---- 5. Evidence paths + approval-year ONLY for the top_k ---- #
        results: list[RepurposeResult] = []
        for d in top:
            edge = self.kg.treats_edge.get((d, disease_id))
            approval_year = edge.get("approval_year") if edge else None
            is_approved = (d, disease_id) in self.treats_set
            paths = self.kg.evidence_paths(d, disease_id, k=3, max_paths=3)
            results.append(
                RepurposeResult(
                    drug_id=d,
                    drug_name=self.kg.node_by_id[d]["name"],
                    model_score=model_score_of[d],
                    graph_score=graph_score_of[d],
                    fused_score=rrf(d),
                    model_rank=model_rank_of[d],
                    graph_rank=graph_rank_of[d],
                    already_approved=is_approved,
                    approval_year=approval_year,
                    evidence_paths=paths,
                )
            )
        return results


def build_default_service() -> RepurposeService:
    from app.kg.loader import load_kg

    kg = load_kg()
    E, R, _ = kge_mod.load_for_kg(kg)
    return RepurposeService(kg, E, R)


if __name__ == "__main__":
    # Run as a module for correct package resolution:
    #     python -m app.repurpose.service
    svc = build_default_service()
    for dis in ["D:GAUCHER", "D:NPC", "D:FABRY"]:
        print(f"\n--- Repurposing candidates for {svc.kg.node_by_id[dis]['name']} ---")
        for r in svc.predict(dis, top_k=5, include_already_approved=False):
            tag = " [approved]" if r.already_approved else ""
            print(
                f"  #{r.model_rank:2d}m / #{r.graph_rank:2d}g  {r.drug_name:28s}"
                f"  model={r.model_score:+.3f} graph={r.graph_score:.3f} "
                f"rrf={r.fused_score:.4f}{tag}"
            )
            for p in r.evidence_paths[:1]:
                chain = " -> ".join(
                    f"[{x['rel']}:{x['direction']}] {svc.kg.node_by_id[x['to']]['name']}" for x in p
                )
                print(f"        via: {svc.kg.node_by_id[p[0]['from']]['name']} {chain}")

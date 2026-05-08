"""
Drug-repurposing inference service.

Inputs : disease_id, top_k, include_already_approved, model
Outputs: ranked list of drug candidates with:
          - model score
              * RotatE   (default): -||h o r - t||_2 in complex space
              * R-GCN / CompGCN: DistMult head over message-passed embeddings
          - graph evidence score (pathway-overlap Jaccard)
          - fused score (reciprocal-rank fusion, k=60)
          - evidence subgraph (short paths drug -> disease)
          - whether the (drug, disease) edge is already in the KG
            (UI dims "already approved" vs "novel prediction")

The model is selected per request via the optional `model` field on
RepurposeRequest. If a requested model's artifacts are not loaded (e.g.
the GNN training notebook hasn't been run yet), the service raises
`ModelUnavailableError` and the router returns 503.

Ranking semantics:
  Approved drugs are filtered OUT of the candidate set BEFORE ranking
  when `include_already_approved=False`, so `model_rank` and `graph_rank`
  match the returned ordering.

Graph score: drug-side walker is filtered to `rel == "TARGETS"`; disease
side walks `(CAUSES|ASSOCIATED_WITH) -> ENCODES -> PARTICIPATES_IN`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from app.kg.loader import KG
from app.ml import distmult, rotate


class ModelUnavailableError(KeyError):
    """The caller asked for a model whose artifacts aren't loaded."""


@dataclass
class _ModelHead:
    """One scoring head: (E, R) tables + a `rank_heads` function.

    `rank_heads(E, R, r_idx, t_idx, candidate_heads)` -> (sorted_ids, sorted_scores).
    """

    name: str
    E: np.ndarray
    R: np.ndarray
    rank_heads: Callable[[np.ndarray, np.ndarray, int, int, np.ndarray], tuple[np.ndarray, np.ndarray]]


@dataclass
class RepurposeResult:
    drug_id: str
    drug_name: str
    model_score: float
    graph_score: float
    fused_score: float
    model_rank: int
    graph_rank: int
    already_approved: bool
    approval_year: int | None
    evidence_paths: list[list[dict[str, Any]]]


class RepurposeService:
    def __init__(
        self,
        kg: KG,
        E: np.ndarray,
        R: np.ndarray,
        *,
        extra_models: dict[str, _ModelHead] | None = None,
        default_model: str = "rotate",
    ) -> None:
        self.kg = kg
        # The "rotate" head is always present (RotatE is the canonical model
        # the lifespan loads). Additional models (rgcn / compgcn) are added
        # by the lifespan when their artifacts exist on disk.
        self._models: dict[str, _ModelHead] = {
            "rotate": _ModelHead(
                name="rotate",
                E=E,
                R=R,
                rank_heads=rotate.rank_heads,
            ),
        }
        if extra_models:
            self._models.update(extra_models)
        self._default_model = default_model

        # Known TREATS set for "already_approved" flag.
        self.treats_set: set[tuple[str, str]] = set(kg.treats_edge.keys())

        # Drug -> set of pathway ids (via TARGETS -> PARTICIPATES_IN).
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

        # Disease -> set of pathway ids
        # (via (CAUSES|ASSOCIATED_WITH) -> ENCODES -> PARTICIPATES_IN).
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

    # ------------------------------------------------------------------ #
    # Public read API
    # ------------------------------------------------------------------ #

    @property
    def available_models(self) -> list[str]:
        return sorted(self._models.keys())

    def has_model(self, name: str) -> bool:
        return name in self._models

    def predict(
        self,
        disease_id: str,
        top_k: int = 10,
        include_already_approved: bool = False,
        model: str | None = None,
    ) -> list[RepurposeResult]:
        if disease_id not in self.kg.node_by_id:
            raise KeyError(f"Unknown disease id: {disease_id}")

        model_name = model or self._default_model
        head = self._models.get(model_name)
        if head is None:
            raise ModelUnavailableError(
                f"Model {model_name!r} is not loaded. Available: {self.available_models}"
            )

        # ---- 1. Candidate set determined up front ---- #
        if include_already_approved:
            candidates = list(self.kg.drugs)
        else:
            candidates = [d for d in self.kg.drugs if (d, disease_id) not in self.treats_set]
        candidates.sort()  # Deterministic tie-breaking
        if not candidates:
            return []

        cand_idxs = np.array([self.kg.entity_to_idx[d] for d in candidates], dtype=np.int64)

        # ---- 2. Model scores ---- #
        r_idx = self.kg.relation_to_idx["TREATS"]
        dis_idx = self.kg.entity_to_idx[disease_id]
        ranked_idx, ranked_scores = head.rank_heads(head.E, head.R, r_idx, dis_idx, cand_idxs)
        model_score_of = {
            self.kg.idx_to_entity[int(e)]: float(s)
            for e, s in zip(ranked_idx, ranked_scores, strict=False)
        }
        model_ranked = sorted(candidates, key=lambda d: (-model_score_of[d], d))
        model_rank_of = {d: i + 1 for i, d in enumerate(model_ranked)}

        # ---- 3. Graph scores ---- #
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

        # ---- 4. Fuse via RRF (k=60) ---- #
        def rrf(d: str) -> float:
            return 1.0 / (60 + model_rank_of[d]) + 1.0 / (60 + graph_rank_of[d])

        fused_order = sorted(candidates, key=lambda d: (-rrf(d), d))
        top = fused_order[:top_k]

        # ---- 5. Evidence paths + approval-year for top_k only ---- #
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


def _try_load_distmult_model(name: str, kg: KG) -> _ModelHead | None:
    """Best-effort loader for an optional R-GCN / CompGCN artifact.

    Returns None silently if the artifact isn't on disk yet (the user
    hasn't run the Colab notebook). Raises if the artifact exists but
    is stale -- that's a real bug we want loud.
    """
    try:
        E, R, _meta = distmult.load_for_kg(name, kg)
    except FileNotFoundError:
        return None
    return _ModelHead(name=name, E=E, R=R, rank_heads=distmult.rank_heads)


def build_default_service() -> RepurposeService:
    """CLI / dev entry-point. Loads RotatE + any DistMult-scored GNN
    artifacts that happen to be on disk."""
    from app.kg.loader import load_kg

    kg = load_kg()
    E, R, _ = rotate.load_for_kg(kg)
    extras: dict[str, _ModelHead] = {}
    for name in ("rgcn", "compgcn"):
        head = _try_load_distmult_model(name, kg)
        if head is not None:
            extras[name] = head
    return RepurposeService(kg, E, R, extra_models=extras)


if __name__ == "__main__":
    svc = build_default_service()
    print(f"Available models: {svc.available_models}")
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
                    f"[{x['rel']}:{x['direction']}] {svc.kg.node_by_id[x['to']]['name']}"
                    for x in p
                )
                print(f"        via: {svc.kg.node_by_id[p[0]['from']]['name']} {chain}")

"""
Held-out evaluator for the TransE TREATS predictor.

Why this file exists:
  The previous "performance" numbers in README.md (Hits@1 / MRR / sample rank)
  were computed on triples the model had been trained on. That is training-set
  leakage -- the single most damaging defect in the MVP for thesis / workshop
  credibility. This file replaces those numbers with a proper leave-one-out
  evaluation and writes the result to `data/artifacts/eval_report.json`.

Protocol (Bordes-2013 / PyKEEN convention, filtered ranking):
  For each of the N TREATS triples (h, TREATS, t):
    1. Retrain TransE on the other N-1 triples (plus every non-TREATS triple),
       so the held-out fact is not in the training set.
    2. Score every Drug as a possible head for (TREATS, t).
    3. Remove other *known-true* TREATS heads for the same t from the ranking
       (filtered protocol -- else rare tails with 2-3 approved drugs would
       artificially hurt the score).
    4. Record the rank of the held-out head.
  Aggregate: filtered MRR, Hits@1, Hits@3, Hits@10.

This takes ~2 min on the seed (800 epochs * 16 retrains on a tiny NumPy
graph). In Phase 2 the TransE retrain is replaced by a PyKEEN pipeline
with a time-split on `approval_year`; everything else in this file is
reused verbatim.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict

import numpy as np

from app.core.paths import ARTIFACTS_DIR as ARTIFACTS
from app.kg.loader import KG, load_kg
from app.ml import transe as transe_mod
from app.ml.transe import TransEConfig


def _treats_triples(kg: KG) -> list[tuple[int, int, int]]:
    """Return (h_idx, r_idx, t_idx) for every TREATS edge, in a stable order
    (head canonical-id ascending, then tail)."""
    r = kg.relation_to_idx["TREATS"]
    out: list[tuple[int, int, int]] = []
    for e in kg.triples_with_props:
        if e["rel"] != "TREATS":
            continue
        out.append((kg.entity_to_idx[e["head"]], r, kg.entity_to_idx[e["tail"]]))
    out.sort(key=lambda ht: (kg.idx_to_entity[ht[0]], kg.idx_to_entity[ht[2]]))
    return out


def _filtered_rank(
    E: np.ndarray,
    R: np.ndarray,
    candidate_heads: np.ndarray,
    r_idx: int,
    t_idx: int,
    true_head: int,
    known_heads_for_tail: set[int],
) -> int:
    """Filtered rank of `true_head` among `candidate_heads` for (r, t).
    Other known-true heads for the same tail are excluded from the ranking
    so ties to siblings do not falsely penalize the model."""
    ranked, _ = transe_mod.rank_heads(E, R, r_idx, t_idx, candidate_heads)
    rank = 0
    for h in ranked:
        h_int = int(h)
        if h_int == true_head:
            return rank + 1
        if h_int in known_heads_for_tail and h_int != true_head:
            continue  # filtered
        rank += 1
    raise RuntimeError("true head not in candidate set")


def evaluate(
    kg: KG,
    cfg: TransEConfig | None = None,
    verbose: bool = True,
) -> dict:
    cfg = cfg or TransEConfig()
    treats = _treats_triples(kg)
    n_entities = len(kg.idx_to_entity)
    n_relations = len(kg.idx_to_relation)
    drug_idxs = np.array([kg.entity_to_idx[d] for d in kg.drugs], dtype=np.int64)

    # Pre-build the filter set: for each tail t, all known TREATS heads.
    heads_for_tail: dict[int, set[int]] = {}
    for h, _, t in treats:
        heads_for_tail.setdefault(t, set()).add(h)

    all_triples = list(kg.triples)
    ranks: list[int] = []
    per_item: list[dict] = []
    t0 = time.time()

    for i, (h, r, t) in enumerate(treats):
        train = [trp for trp in all_triples if trp != (h, r, t)]
        if verbose:
            print(
                f"  [{i + 1}/{len(treats)}] hold-out "
                f"{kg.idx_to_entity[h]} -TREATS-> {kg.idx_to_entity[t]}",
                flush=True,
            )
        E, R, _ = transe_mod.train(train, n_entities, n_relations, cfg=cfg, verbose=False)
        rank = _filtered_rank(
            E,
            R,
            drug_idxs,
            r,
            t,
            true_head=h,
            known_heads_for_tail=heads_for_tail[t],
        )
        ranks.append(rank)
        per_item.append(
            {
                "head": kg.idx_to_entity[h],
                "tail": kg.idx_to_entity[t],
                "head_name": kg.node_by_id[kg.idx_to_entity[h]]["name"],
                "tail_name": kg.node_by_id[kg.idx_to_entity[t]]["name"],
                "rank": rank,
                "n_candidates": int(len(drug_idxs) - (len(heads_for_tail[t]) - 1)),
            }
        )

    ranks_arr = np.asarray(ranks, dtype=np.float64)
    metrics = {
        "n_evaluated": len(ranks),
        "n_candidates_per_eval": len(drug_idxs),
        "mean_rank": float(ranks_arr.mean()),
        "mrr": float((1.0 / ranks_arr).mean()),
        "hits_at_1": float((ranks_arr <= 1).mean()),
        "hits_at_3": float((ranks_arr <= 3).mean()),
        "hits_at_10": float((ranks_arr <= 10).mean()),
        "ranks": ranks,
    }
    if verbose:
        print(f"\n  eval done in {time.time() - t0:.1f}s across {len(ranks)} held-out triples")
    return {
        "protocol": (
            "leave-one-out over TREATS triples; filtered rank over all Drug "
            "heads; other known TREATS heads for the same tail excluded."
        ),
        "kg_version": kg.version,
        "config": asdict(cfg),
        "metrics": metrics,
        "per_item": per_item,
    }


def main() -> int:
    kg = load_kg()
    print(
        f"Evaluating TransE (leave-one-out over TREATS) on KG {kg.version} "
        f"-- {len(kg.idx_to_entity)} entities, {len(kg.triples)} triples"
    )
    report = evaluate(kg)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / "eval_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    m = report["metrics"]
    print("\n=== Held-out TransE evaluation ===")
    print(f"  Protocol       : {report['protocol']}")
    print(f"  KG version     : {report['kg_version']}")
    print(f"  N held-out     : {m['n_evaluated']}")
    print(f"  N candidates   : {m['n_candidates_per_eval']}")
    print(f"  Mean rank      : {m['mean_rank']:.2f}")
    print(f"  MRR (filtered) : {m['mrr']:.3f}")
    print(f"  Hits@1         : {m['hits_at_1']:.3f}")
    print(f"  Hits@3         : {m['hits_at_3']:.3f}")
    print(f"  Hits@10        : {m['hits_at_10']:.3f}")
    print(f"\n  Report written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

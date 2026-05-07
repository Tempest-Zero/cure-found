"""
Held-out evaluator for the RotatE TREATS predictor.

Why this file exists:
  The previous "performance" numbers in README.md (Hits@1 / MRR / sample rank)
  were computed on triples the model had been trained on. That is training-set
  leakage -- the single most damaging defect in the MVP for thesis / workshop
  credibility. This file replaces those numbers with a proper leave-one-out
  evaluation and writes the result to `data/artifacts/eval_report.json`.

Protocol (Sun-2019 / PyKEEN convention, filtered ranking):
  For each of the N TREATS triples (h, TREATS, t):
    1. Retrain RotatE on the other N-1 triples (plus every non-TREATS triple),
       so the held-out fact is not in the training set.
    2. Score every Drug as a possible head for (TREATS, t).
    3. Remove other *known-true* TREATS heads for the same t from the ranking
       (filtered protocol -- else rare tails with 2-3 approved drugs would
       artificially hurt the score).
    4. Record the rank of the held-out head.
  Aggregate: filtered MRR, Hits@1, Hits@3, Hits@10, plus a non-parametric
  bootstrap-95% CI computed over the per-triple ranks.

In Phase 2 the RotatE retrain is replaced by a PyKEEN pipeline with a
time-split on `approval_year`; everything else in this file is reused
verbatim.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, replace

import numpy as np

from app.core.paths import ARTIFACTS_DIR as ARTIFACTS
from app.kg.loader import KG, load_kg
from app.ml import rotate as kge_mod
from app.ml.rotate import RotatEConfig


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
    ranked, _ = kge_mod.rank_heads(E, R, r_idx, t_idx, candidate_heads)
    rank = 0
    for h in ranked:
        h_int = int(h)
        if h_int == true_head:
            return rank + 1
        if h_int in known_heads_for_tail and h_int != true_head:
            continue  # filtered
        rank += 1
    raise RuntimeError("true head not in candidate set")


def _bootstrap_ci(
    ranks: list[int],
    *,
    n_resamples: int = 2000,
    seed: int = 42,
    alpha: float = 0.05,
) -> dict:
    """Non-parametric bootstrap 95% CI on MRR / Hits@K / mean rank.

    With n=16 leave-one-out triples, point estimates have ±0.06 swing per
    triple (1/16). Bootstrapping makes that uncertainty visible so the
    evaluation isn't pretending to a precision it doesn't have.
    """
    rng = np.random.default_rng(seed)
    arr = np.asarray(ranks, dtype=np.float64)
    n = len(arr)
    if n == 0:
        return {}
    metrics = {"mrr": [], "hits_at_1": [], "hits_at_3": [], "hits_at_10": [], "mean_rank": []}
    for _ in range(n_resamples):
        idxs = rng.integers(0, n, size=n)
        sample = arr[idxs]
        metrics["mrr"].append(float((1.0 / sample).mean()))
        metrics["hits_at_1"].append(float((sample <= 1).mean()))
        metrics["hits_at_3"].append(float((sample <= 3).mean()))
        metrics["hits_at_10"].append(float((sample <= 10).mean()))
        metrics["mean_rank"].append(float(sample.mean()))

    lo_pct = 100 * (alpha / 2)
    hi_pct = 100 * (1 - alpha / 2)
    ci = {}
    for k, vals in metrics.items():
        v = np.asarray(vals)
        ci[k] = {
            "mean": float(v.mean()),
            "lo": float(np.percentile(v, lo_pct)),
            "hi": float(np.percentile(v, hi_pct)),
            "std": float(v.std(ddof=1)),
        }
    ci["_meta"] = {
        "n_resamples": n_resamples,
        "alpha": alpha,
        "n_triples": n,
        "seed": seed,
    }
    return ci


def evaluate(
    kg: KG,
    cfg: RotatEConfig | None = None,
    verbose: bool = True,
    bootstrap_resamples: int = 2000,
) -> dict:
    cfg = cfg or RotatEConfig()
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
        E, R, _ = kge_mod.train(train, n_entities, n_relations, cfg=cfg, verbose=False)
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
    ci = _bootstrap_ci(ranks, n_resamples=bootstrap_resamples)
    if verbose:
        print(f"\n  eval done in {time.time() - t0:.1f}s across {len(ranks)} held-out triples")
    return {
        "model": "RotatE",
        "protocol": (
            "leave-one-out over TREATS triples; filtered rank over all Drug "
            "heads; other known TREATS heads for the same tail excluded."
        ),
        "kg_version": kg.version,
        "config": asdict(cfg),
        "metrics": metrics,
        "bootstrap_ci_95": ci,
        "per_item": per_item,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="eval", description="Leave-one-out RotatE eval")
    p.add_argument(
        "--epochs",
        type=int,
        default=None,
        help="Override RotatEConfig.epochs (default: use cfg default 1000). "
        "Useful for the larger expanded KG where convergence is faster.",
    )
    p.add_argument(
        "--bootstrap",
        type=int,
        default=2000,
        help="Number of bootstrap resamples for the CI (default 2000).",
    )
    p.add_argument(
        "--out",
        type=str,
        default=None,
        help="Path to write the report (default: data/artifacts/eval_report.json).",
    )
    args = p.parse_args(argv)

    kg = load_kg()
    cfg = RotatEConfig()
    if args.epochs is not None:
        cfg = replace(cfg, epochs=args.epochs)

    print(
        f"Evaluating RotatE (leave-one-out over TREATS) on KG {kg.version} "
        f"-- {len(kg.idx_to_entity)} entities, {len(kg.triples)} triples"
    )
    print(
        f"Config: epochs={cfg.epochs} dim={cfg.dim} batch={cfg.batch_size} negs={cfg.neg_per_pos}"
    )

    report = evaluate(kg, cfg=cfg, bootstrap_resamples=args.bootstrap)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = (
        ARTIFACTS / "eval_report.json"
        if args.out is None
        else (ARTIFACTS.parent / args.out).resolve()
    )
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    m = report["metrics"]
    ci = report["bootstrap_ci_95"]
    print("\n=== Held-out RotatE evaluation ===")
    print(f"  Protocol       : {report['protocol']}")
    print(f"  KG version     : {report['kg_version']}")
    print(f"  N held-out     : {m['n_evaluated']}")
    print(f"  N candidates   : {m['n_candidates_per_eval']}")
    print(
        f"  Mean rank      : {m['mean_rank']:.2f}  [{ci['mean_rank']['lo']:.2f}, {ci['mean_rank']['hi']:.2f}]"
    )
    print(f"  MRR (filtered) : {m['mrr']:.3f}  [{ci['mrr']['lo']:.3f}, {ci['mrr']['hi']:.3f}]")
    print(
        f"  Hits@1         : {m['hits_at_1']:.3f}  [{ci['hits_at_1']['lo']:.3f}, {ci['hits_at_1']['hi']:.3f}]"
    )
    print(
        f"  Hits@3         : {m['hits_at_3']:.3f}  [{ci['hits_at_3']['lo']:.3f}, {ci['hits_at_3']['hi']:.3f}]"
    )
    print(
        f"  Hits@10        : {m['hits_at_10']:.3f}  [{ci['hits_at_10']['lo']:.3f}, {ci['hits_at_10']['hi']:.3f}]"
    )
    print(f"\n  Report written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Train R-GCN and CompGCN on the CureFound KG via PyKEEN.

This script is designed to be run on Google Colab (T4 GPU) but works
locally on CPU too. It produces:

  data/artifacts/rgcn.npz          — R-GCN entity + relation embeddings
  data/artifacts/rgcn_meta.json    — vocab digest + config + KG version
  data/artifacts/compgcn.npz       — CompGCN entity + relation embeddings
  data/artifacts/compgcn_meta.json — same shape as rgcn_meta.json
  data/artifacts/eval_report_rgcn.json
  data/artifacts/eval_report_compgcn.json

Each model is:
  1. Trained once on the full KG (saved as the production artifact).
  2. Evaluated via 16-fold leave-one-out over TREATS triples, filtered
     ranking against all 19 Drug heads, with bootstrap-95% CIs.

Both models use **DistMult interaction** at the scoring layer so we can
score in pure NumPy at inference time:

    score(h, r, t) = sum_d  h_d * r_d * t_d

i.e. no PyTorch needed in the production container — same trick we use
for RotatE.

Run:
    python scripts/train_gnns_pykeen.py
    python scripts/train_gnns_pykeen.py --models rgcn         # one model only
    python scripts/train_gnns_pykeen.py --epochs 200          # cheaper
    python scripts/train_gnns_pykeen.py --skip-eval           # train only

Colab usage (see scripts/colab_gnn_training.ipynb):
    !git clone https://github.com/Tempest-Zero/cure-found.git
    %cd cure-found/curefound
    !pip install -q pykeen
    !python scripts/train_gnns_pykeen.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SEED_KG = ROOT / "data" / "seed" / "kg.json"
ARTIFACTS = ROOT / "data" / "artifacts"


# ---------------------------------------------------------------------------
# KG loading (shape-compatible with app/kg/loader.py without the dep)
# ---------------------------------------------------------------------------


@dataclass
class MiniKG:
    """Just enough of `app.kg.loader.KG` for PyKEEN training + LOO eval."""

    triples: list[tuple[str, str, str]]
    nodes: list[dict]
    diseases: list[str]
    drugs: list[str]
    version: str
    idx_to_entity: list[str] = field(init=False)
    entity_to_idx: dict[str, int] = field(init=False)
    idx_to_relation: list[str] = field(init=False)
    relation_to_idx: dict[str, int] = field(init=False)

    def __post_init__(self) -> None:
        self.idx_to_entity = sorted({h for h, _, _ in self.triples} | {t for _, _, t in self.triples})
        self.entity_to_idx = {e: i for i, e in enumerate(self.idx_to_entity)}
        self.idx_to_relation = sorted({r for _, r, _ in self.triples})
        self.relation_to_idx = {r: i for i, r in enumerate(self.idx_to_relation)}


def _vocab_digest(idx_to_entity: list[str]) -> str:
    """Match app/ml/rotate.py's digest format so both artifacts use the
    same staleness-detection scheme."""
    blob = json.dumps(sorted(idx_to_entity), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def load_minikg(path: Path = SEED_KG) -> MiniKG:
    raw = json.loads(path.read_text(encoding="utf-8"))
    triples = [(e["head"], e["rel"], e["tail"]) for e in raw["edges"]]
    diseases = [n["id"] for n in raw["nodes"] if n["type"] == "Disease"]
    drugs = [n["id"] for n in raw["nodes"] if n["type"] == "Drug"]
    version = raw.get("kg_version") or "kg-mvp-0.1"
    return MiniKG(triples=triples, nodes=raw["nodes"], diseases=diseases, drugs=drugs, version=version)


# ---------------------------------------------------------------------------
# PyKEEN training adapter
# ---------------------------------------------------------------------------


def _ensure_pykeen() -> Any:
    try:
        import pykeen  # noqa: F401

        return pykeen
    except ImportError as exc:
        raise SystemExit(
            "PyKEEN is not installed. Run `pip install pykeen` first.\n"
            "On Colab this happens automatically when you !pip install pykeen."
        ) from exc


def _build_factory(triples: list[tuple[str, str, str]], kg: MiniKG):
    """Build a PyKEEN TriplesFactory using KG's existing entity/relation
    vocabulary so all folds share the same id space (otherwise the held-out
    triple's head/tail might not exist in the fold's reduced vocabulary)."""
    from pykeen.triples import TriplesFactory  # type: ignore[import-untyped]

    arr = np.array([[h, r, t] for h, r, t in triples], dtype=str)
    return TriplesFactory.from_labeled_triples(
        triples=arr,
        entity_to_id=kg.entity_to_idx,
        relation_to_id=kg.relation_to_idx,
        create_inverse_triples=False,
    )


def _train_pykeen_model(
    model_name: str,
    triples: list[tuple[str, str, str]],
    kg: MiniKG,
    *,
    epochs: int,
    dim: int,
    device: str,
    seed: int = 42,
) -> Any:
    """Train an R-GCN / CompGCN model via PyKEEN's pipeline. Returns the
    fitted PyTorch model so we can pull embeddings out."""
    from pykeen.pipeline import pipeline  # type: ignore[import-untyped]

    tf = _build_factory(triples, kg)

    # Pipeline kwargs differ slightly per model — DistMult interaction is
    # the simplest scoring head that has a known closed-form NumPy version.
    model_kwargs: dict[str, Any] = {"embedding_dim": dim}

    result = pipeline(
        training=tf,
        validation=tf,  # tiny graph -- no real held-out set; we LOO-eval ourselves
        testing=tf,
        model=model_name,
        model_kwargs=model_kwargs,
        training_kwargs={"num_epochs": epochs, "batch_size": 256},
        optimizer="Adam",
        optimizer_kwargs={"lr": 1e-3},
        loss="NSSALoss",
        random_seed=seed,
        device=device,
        evaluation_kwargs={"use_tqdm": False},
        use_tqdm=False,
    )
    return result.model


def _extract_embeddings(model: Any, kg: MiniKG) -> tuple[np.ndarray, np.ndarray]:
    """Pull entity + relation embeddings out of a fitted PyKEEN model.

    We assume the model uses simple per-entity / per-relation embedding
    representations (true for both RGCN and CompGCN with default config —
    they wrap the message-passing output with a per-node embedding head).

    Returns (entity_emb [n_entities, dim], relation_emb [n_relations, dim])
    both as float32 numpy arrays.
    """
    import torch  # noqa: F401

    model.eval()
    e_repr = model.entity_representations[0]
    r_repr = model.relation_representations[0]

    # Materialise full embedding tables — PyKEEN allows .__call__(indices=None)
    # which returns the full (n, dim) tensor.
    with __import__("torch").no_grad():
        E = e_repr(indices=None).detach().cpu().numpy().astype(np.float32)
        R = r_repr(indices=None).detach().cpu().numpy().astype(np.float32)

    # Some PyKEEN models store complex embeddings — flatten the trailing dim.
    if E.ndim == 3:
        E = E.reshape(E.shape[0], -1)
    if R.ndim == 3:
        R = R.reshape(R.shape[0], -1)

    assert E.shape[0] == len(kg.idx_to_entity), f"E shape {E.shape}"
    assert R.shape[0] == len(kg.idx_to_relation), f"R shape {R.shape}"
    return E, R


def _distmult_score(E: np.ndarray, R: np.ndarray, h_idx, r_idx: int, t_idx: int) -> np.ndarray:
    """DistMult: score(h, r, t) = sum_d  h_d * r_d * t_d.
    Higher = more plausible. Vectorised over h_idx (used for head ranking).
    """
    h = E[h_idx]
    r = R[r_idx]
    t = E[t_idx]
    if h.ndim == 2:
        return (h * r[None, :] * t[None, :]).sum(axis=-1)
    return float((h * r * t).sum())


# ---------------------------------------------------------------------------
# Leave-one-out eval (mirrors app/ml/eval.py exactly)
# ---------------------------------------------------------------------------


def _treats_triples(kg: MiniKG) -> list[tuple[int, int, int]]:
    r_idx = kg.relation_to_idx["TREATS"]
    out: list[tuple[int, int, int]] = []
    for h, r, t in kg.triples:
        if r != "TREATS":
            continue
        out.append((kg.entity_to_idx[h], r_idx, kg.entity_to_idx[t]))
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
    scores = _distmult_score(E, R, candidate_heads, r_idx, t_idx)
    order = np.argsort(-scores)
    ranked = candidate_heads[order]
    rank = 0
    for h in ranked:
        h_int = int(h)
        if h_int == true_head:
            return rank + 1
        if h_int in known_heads_for_tail and h_int != true_head:
            continue
        rank += 1
    raise RuntimeError("true head not in candidate set")


def _bootstrap_ci(ranks: list[int], *, n_resamples: int = 2000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    arr = np.asarray(ranks, dtype=np.float64)
    n = len(arr)
    if n == 0:
        return {}
    keys = ("mrr", "hits_at_1", "hits_at_3", "hits_at_10", "mean_rank")
    samples: dict[str, list[float]] = {k: [] for k in keys}
    for _ in range(n_resamples):
        s = arr[rng.integers(0, n, size=n)]
        samples["mrr"].append(float((1.0 / s).mean()))
        samples["hits_at_1"].append(float((s <= 1).mean()))
        samples["hits_at_3"].append(float((s <= 3).mean()))
        samples["hits_at_10"].append(float((s <= 10).mean()))
        samples["mean_rank"].append(float(s.mean()))
    ci: dict[str, dict[str, float]] = {}
    for k, vals in samples.items():
        v = np.asarray(vals)
        ci[k] = {
            "mean": float(v.mean()),
            "lo": float(np.percentile(v, 2.5)),
            "hi": float(np.percentile(v, 97.5)),
            "std": float(v.std(ddof=1)),
        }
    ci["_meta"] = {"n_resamples": n_resamples, "n_triples": n, "seed": seed}
    return ci


def loo_eval(
    model_name: str,
    kg: MiniKG,
    *,
    epochs: int,
    dim: int,
    device: str,
    bootstrap: int = 2000,
) -> dict:
    treats = _treats_triples(kg)
    drug_idxs = np.array([kg.entity_to_idx[d] for d in kg.drugs], dtype=np.int64)
    heads_for_tail: dict[int, set[int]] = {}
    for h, _, t in treats:
        heads_for_tail.setdefault(t, set()).add(h)

    all_triples = list(kg.triples)
    ranks: list[int] = []
    per_item: list[dict] = []
    t0 = time.time()

    for i, (h, r, t) in enumerate(treats):
        held_triple = (
            kg.idx_to_entity[h],
            kg.idx_to_relation[r],
            kg.idx_to_entity[t],
        )
        train_triples = [trp for trp in all_triples if trp != held_triple]
        print(
            f"  [{i + 1}/{len(treats)}] hold-out "
            f"{kg.idx_to_entity[h]} -TREATS-> {kg.idx_to_entity[t]}  ({model_name})",
            flush=True,
        )
        model = _train_pykeen_model(
            model_name,
            train_triples,
            kg,
            epochs=epochs,
            dim=dim,
            device=device,
        )
        E, R = _extract_embeddings(model, kg)
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
                "head_name": next((n["name"] for n in kg.nodes if n["id"] == kg.idx_to_entity[h]), kg.idx_to_entity[h]),
                "tail_name": next((n["name"] for n in kg.nodes if n["id"] == kg.idx_to_entity[t]), kg.idx_to_entity[t]),
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
    return {
        "model": model_name,
        "interaction": "DistMult",
        "protocol": "leave-one-out over TREATS, filtered rank, head ranking only",
        "kg_version": kg.version,
        "config": {"dim": dim, "epochs": epochs, "device": device},
        "wall_time_s": round(time.time() - t0, 1),
        "metrics": metrics,
        "bootstrap_ci_95": _bootstrap_ci(ranks, n_resamples=bootstrap),
        "per_item": per_item,
    }


# ---------------------------------------------------------------------------
# Production-artifact training (full data, saved for the API server)
# ---------------------------------------------------------------------------


def train_and_save(
    model_name: str,
    kg: MiniKG,
    *,
    epochs: int,
    dim: int,
    device: str,
) -> tuple[Path, Path]:
    print(f"\n=== Training {model_name} on full KG ({epochs} epochs, dim={dim}, device={device}) ===")
    t0 = time.time()
    model = _train_pykeen_model(model_name, kg.triples, kg, epochs=epochs, dim=dim, device=device)
    E, R = _extract_embeddings(model, kg)
    elapsed = time.time() - t0

    short = model_name.lower().replace("-", "")
    npz_path = ARTIFACTS / f"{short}.npz"
    meta_path = ARTIFACTS / f"{short}_meta.json"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    np.savez(npz_path, E=E, R=R)
    meta = {
        "model": model_name,
        "interaction": "DistMult",
        "kg_version": kg.version,
        "entity_vocab_sha256": _vocab_digest(kg.idx_to_entity),
        "n_entities": len(kg.idx_to_entity),
        "n_relations": len(kg.idx_to_relation),
        "idx_to_entity": kg.idx_to_entity,
        "idx_to_relation": kg.idx_to_relation,
        "config": {"dim": dim, "epochs": epochs, "device": device},
        "train_time_s": round(elapsed, 1),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"  -> saved {npz_path.name} (E {E.shape}) and {meta_path.name} in {elapsed:.1f}s")
    return npz_path, meta_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="train_gnns_pykeen")
    p.add_argument(
        "--models",
        default="rgcn,compgcn",
        help="Comma-separated subset of {rgcn,compgcn}",
    )
    p.add_argument("--epochs", type=int, default=300)
    p.add_argument("--dim", type=int, default=64)
    p.add_argument("--bootstrap", type=int, default=2000)
    p.add_argument("--device", default="auto", help="auto|cpu|cuda")
    p.add_argument("--skip-eval", action="store_true", help="Train only, skip LOO eval")
    p.add_argument("--seed", type=Path, default=SEED_KG)
    args = p.parse_args(argv)

    _ensure_pykeen()

    if args.device == "auto":
        try:
            import torch  # type: ignore[import-untyped]

            args.device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            args.device = "cpu"
    print(f"Using device: {args.device}")

    kg = load_minikg(args.seed)
    print(f"KG: {len(kg.idx_to_entity)} entities, {len(kg.idx_to_relation)} relations, {len(kg.triples)} triples")

    name_map = {"rgcn": "RGCN", "compgcn": "CompGCN"}
    targets = [name_map[m.strip().lower()] for m in args.models.split(",")]

    for model_name in targets:
        train_and_save(model_name, kg, epochs=args.epochs, dim=args.dim, device=args.device)

        if args.skip_eval:
            continue

        print(f"\n=== LOO eval for {model_name} ({args.epochs} epochs/fold) ===")
        report = loo_eval(
            model_name,
            kg,
            epochs=args.epochs,
            dim=args.dim,
            device=args.device,
            bootstrap=args.bootstrap,
        )
        out = ARTIFACTS / f"eval_report_{model_name.lower().replace('-', '')}.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        m = report["metrics"]
        ci = report["bootstrap_ci_95"]
        print(f"\n=== {model_name} eval done ===")
        print(f"  MRR     : {m['mrr']:.3f}  [{ci['mrr']['lo']:.3f}, {ci['mrr']['hi']:.3f}]")
        print(f"  Hits@1  : {m['hits_at_1']:.3f}  [{ci['hits_at_1']['lo']:.3f}, {ci['hits_at_1']['hi']:.3f}]")
        print(f"  Hits@3  : {m['hits_at_3']:.3f}  [{ci['hits_at_3']['lo']:.3f}, {ci['hits_at_3']['hi']:.3f}]")
        print(f"  Hits@10 : {m['hits_at_10']:.3f}  [{ci['hits_at_10']['lo']:.3f}, {ci['hits_at_10']['hi']:.3f}]")
        print(f"  Mean    : {m['mean_rank']:.2f}  [{ci['mean_rank']['lo']:.2f}, {ci['mean_rank']['hi']:.2f}]")
        print(f"  Saved   : {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

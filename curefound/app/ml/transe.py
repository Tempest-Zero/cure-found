"""
TransE in pure NumPy — MVP embedding trainer.

Why from scratch: avoids a 2 GB PyTorch / PyKEEN install for a graph that
fits on one screen. Same score function and margin-ranking loss as the
original Bordes et al. 2013 paper; readable enough to extend.

Score: f(h, r, t) = -||h + r - t||_2   (higher is better)
Loss:  max(0, margin + f(h',r,t') - f(h,r,t))  with corrupt head or tail

Phase 2 swap: replace the calls from api.services.repurpose / .diagnose
with a PyKEEN pipeline. Public artifact contract stays the same:
    artifacts/transe.npz with arrays:
        E [n_entities, dim]   — entity embeddings (L2-normalized)
        R [n_relations, dim]  — relation embeddings
    artifacts/transe_meta.json with idx_to_entity / idx_to_relation.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

# Anchored at the project root (`curefound/`) via `app.core.paths` -- the
# module's on-disk depth changed in the pre-Phase-1 refactor.
from app.core.paths import ARTIFACTS_DIR as DEFAULT_ARTIFACTS


class ArtifactStaleError(RuntimeError):
    """Raised by `load_for_kg` when the TransE artifact on disk was trained
    against a different KG vocabulary than the one currently loaded. Usually
    means the seed was edited without re-running `python run.py train`
    (addresses H4 in the audit plan)."""


def _vocab_digest(idx_to_entity: list[str]) -> str:
    """SHA-256 over the sorted entity vocabulary. Embedded into the saved
    metadata so we can cheaply detect a KG-edit-without-retrain."""
    blob = json.dumps(sorted(idx_to_entity), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


@dataclass
class TransEConfig:
    dim: int = 64
    margin: float = 1.0
    lr: float = 0.01
    epochs: int = 800
    batch_size: int = 64
    neg_per_pos: int = 4
    seed: int = 42
    # L2-normalize entity embeddings at the start of each epoch (standard TransE trick)
    normalize_entities: bool = True


def _l2_normalize(x: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.maximum(n, eps)


def _score(
    E: np.ndarray, R: np.ndarray, h_idx: np.ndarray, r_idx: np.ndarray, t_idx: np.ndarray
) -> np.ndarray:
    """Higher is better. Returns -||h + r - t||."""
    diff = E[h_idx] + R[r_idx] - E[t_idx]
    return -np.linalg.norm(diff, axis=-1)


def train(
    triples: list[tuple[int, int, int]],
    n_entities: int,
    n_relations: int,
    cfg: TransEConfig | None = None,
    verbose: bool = True,
) -> tuple[np.ndarray, np.ndarray, list[float]]:
    """Train TransE on the given triples. Returns (E, R, loss_history)."""
    cfg = cfg or TransEConfig()
    rng = np.random.default_rng(cfg.seed)

    # Xavier-ish uniform init on [-6/sqrt(dim), 6/sqrt(dim)] per Bordes 2013.
    bound = 6.0 / np.sqrt(cfg.dim)
    E = rng.uniform(-bound, bound, size=(n_entities, cfg.dim)).astype(np.float32)
    R = rng.uniform(-bound, bound, size=(n_relations, cfg.dim)).astype(np.float32)
    R = _l2_normalize(R)  # normalize relations once

    T = np.asarray(triples, dtype=np.int64)  # [n_triples, 3]
    n_triples = T.shape[0]

    # Precompute per-relation (h→set(t)) and (t→set(h)) for filtered corruption.
    rh_to_t: dict[tuple[int, int], set[int]] = {}
    rt_to_h: dict[tuple[int, int], set[int]] = {}
    for h, r, t in triples:
        rh_to_t.setdefault((r, h), set()).add(t)
        rt_to_h.setdefault((r, t), set()).add(h)

    loss_history: list[float] = []
    t0 = time.time()

    for epoch in range(cfg.epochs):
        if cfg.normalize_entities:
            E = _l2_normalize(E)

        # shuffle
        perm = rng.permutation(n_triples)
        epoch_loss = 0.0
        n_batches = 0

        for start in range(0, n_triples, cfg.batch_size):
            batch = T[perm[start : start + cfg.batch_size]]
            bsz = batch.shape[0]
            h, r, t = batch[:, 0], batch[:, 1], batch[:, 2]

            # Generate negatives. For each positive, create neg_per_pos corruptions
            # by replacing head or tail with a random entity (filtered once).
            h_rep = np.repeat(h, cfg.neg_per_pos)
            r_rep = np.repeat(r, cfg.neg_per_pos)
            t_rep = np.repeat(t, cfg.neg_per_pos)
            corrupt_tail = rng.random(h_rep.shape[0]) < 0.5
            neg = rng.integers(0, n_entities, size=h_rep.shape[0])
            # filter: avoid generating true positives (best-effort, one resample)
            for i in range(h_rep.shape[0]):
                if corrupt_tail[i]:
                    if neg[i] in rh_to_t.get((r_rep[i], h_rep[i]), ()):
                        neg[i] = (neg[i] + 1) % n_entities
                else:
                    if neg[i] in rt_to_h.get((r_rep[i], t_rep[i]), ()):
                        neg[i] = (neg[i] + 1) % n_entities
            h_neg = np.where(corrupt_tail, h_rep, neg)
            t_neg = np.where(corrupt_tail, neg, t_rep)

            # Scores (higher = better; loss uses negative => lower = better for grad)
            pos_score = _score(E, R, h_rep, r_rep, t_rep)  # [B*K]
            neg_score = _score(E, R, h_neg, r_rep, t_neg)  # [B*K]
            # margin ranking: loss = max(0, margin - (pos - neg)) = max(0, margin + neg - pos)
            loss_vec = np.maximum(0.0, cfg.margin - (pos_score - neg_score))
            active = loss_vec > 0.0
            if not np.any(active):
                continue
            epoch_loss += float(loss_vec.mean())
            n_batches += 1

            # Gradient: d/dx ||h + r - t|| = (h + r - t) / ||h + r - t||
            # For active samples only. We update both pos and neg terms.
            def grad_norm(h_i, r_i, t_i):
                v = E[h_i] + R[r_i] - E[t_i]  # noqa: B023
                n = np.linalg.norm(v, axis=-1, keepdims=True)
                return v / np.maximum(n, 1e-12)

            # Accumulate grads sparsely via np.add.at
            gE = np.zeros_like(E)
            gR = np.zeros_like(R)

            act_idx = np.where(active)[0]
            if act_idx.size == 0:
                continue

            # For pos: pos_score = -||.||, so d(-pos_score)/d* = +grad_norm(.)
            vp = grad_norm(h_rep[act_idx], r_rep[act_idx], t_rep[act_idx])
            # For neg: we want to decrease neg_score (push pair apart), so d(loss)/d(neg_score) = -1 when active
            # neg_score = -||.||_neg, so d(neg_score)/d* = -grad_norm(.)_neg
            # d(loss)/d* for neg terms = -(-grad_norm_neg) = +grad_norm_neg
            vn = grad_norm(h_neg[act_idx], r_rep[act_idx], t_neg[act_idx])

            # loss = margin + neg_score - pos_score (for active)
            #      = margin - ||neg|| + ||pos||   (since score is -||.||)
            # d(loss)/dE[h_pos] = +grad_norm_pos
            # d(loss)/dE[t_pos] = -grad_norm_pos
            # d(loss)/dR[r]     = +grad_norm_pos - grad_norm_neg
            # d(loss)/dE[h_neg] = -grad_norm_neg
            # d(loss)/dE[t_neg] = +grad_norm_neg
            np.add.at(gE, h_rep[act_idx], vp)
            np.add.at(gE, t_rep[act_idx], -vp)
            np.add.at(gR, r_rep[act_idx], vp - vn)
            np.add.at(gE, h_neg[act_idx], -vn)
            np.add.at(gE, t_neg[act_idx], vn)

            # Average over batch (use bsz*K count)
            denom = float(bsz * cfg.neg_per_pos)
            E -= cfg.lr * gE / denom
            R -= cfg.lr * gR / denom

        mean_loss = epoch_loss / max(n_batches, 1)
        loss_history.append(mean_loss)
        if verbose and (epoch % max(cfg.epochs // 20, 1) == 0 or epoch == cfg.epochs - 1):
            print(
                f"  epoch {epoch + 1:4d}/{cfg.epochs}  loss={mean_loss:.4f}  "
                f"({time.time() - t0:.1f}s)"
            )

    if cfg.normalize_entities:
        E = _l2_normalize(E)
    return E, R, loss_history


def save(
    E: np.ndarray, R: np.ndarray, kg, cfg: TransEConfig, out_dir: Path = DEFAULT_ARTIFACTS
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez(out_dir / "transe.npz", E=E, R=R)
    (out_dir / "transe_meta.json").write_text(
        json.dumps(
            {
                "kg_version": kg.version,
                "entity_vocab_sha256": _vocab_digest(kg.idx_to_entity),
                "n_entities": len(kg.idx_to_entity),
                "n_relations": len(kg.idx_to_relation),
                "idx_to_entity": kg.idx_to_entity,
                "idx_to_relation": kg.idx_to_relation,
                "config": asdict(cfg),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def load(artifacts_dir: Path = DEFAULT_ARTIFACTS) -> tuple[np.ndarray, np.ndarray, dict]:
    with np.load(artifacts_dir / "transe.npz") as z:
        E = z["E"]
        R = z["R"]
    meta = json.loads((artifacts_dir / "transe_meta.json").read_text(encoding="utf-8"))
    return E, R, meta


def load_for_kg(kg, artifacts_dir: Path = DEFAULT_ARTIFACTS) -> tuple[np.ndarray, np.ndarray, dict]:
    """Same as `load`, plus a vocabulary-consistency assertion.

    Raises `ArtifactStaleError` if the entity vocabulary embedded in the
    saved metadata does not match the currently-loaded KG. This is the
    primary guard against "I edited the seed and forgot to retrain" -- the
    embeddings would otherwise be silently indexed into the wrong entity
    slots, producing ranking garbage with no visible error.
    """
    E, R, meta = load(artifacts_dir)
    saved = meta.get("entity_vocab_sha256")
    current = _vocab_digest(kg.idx_to_entity)
    if saved is None:
        # Legacy artifact written before this field existed -- fall back to
        # a direct list comparison so we still catch mismatches.
        if meta.get("idx_to_entity") != kg.idx_to_entity:
            raise ArtifactStaleError(
                "Saved TransE artifact has no entity_vocab_sha256 and its "
                "idx_to_entity does not match the current KG. "
                "Run `python run.py train`."
            )
        return E, R, meta
    if saved != current:
        saved_n = meta.get("n_entities", "?")
        raise ArtifactStaleError(
            f"TransE artifact is stale: saved entity_vocab_sha256={saved[:12]} "
            f"(n={saved_n}) but current KG vocab digest={current[:12]} "
            f"(n={len(kg.idx_to_entity)}). Re-run `python run.py train`."
        )
    return E, R, meta


def rank_tails(
    E: np.ndarray,
    R: np.ndarray,
    h_idx: int,
    r_idx: int,
    candidate_tails: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """For a fixed (h, r), score all candidate tails and return sorted by score desc.
    Returns (sorted_candidate_indices, sorted_scores)."""
    h_vec = E[h_idx]
    r_vec = R[r_idx]
    diff = (h_vec + r_vec)[None, :] - E[candidate_tails]
    scores = -np.linalg.norm(diff, axis=-1)
    order = np.argsort(-scores)
    return candidate_tails[order], scores[order]


def rank_heads(
    E: np.ndarray,
    R: np.ndarray,
    r_idx: int,
    t_idx: int,
    candidate_heads: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    t_vec = E[t_idx]
    r_vec = R[r_idx]
    diff = E[candidate_heads] + r_vec[None, :] - t_vec[None, :]
    scores = -np.linalg.norm(diff, axis=-1)
    order = np.argsort(-scores)
    return candidate_heads[order], scores[order]


if __name__ == "__main__":
    # Run as a module:
    #     python -m app.ml.transe
    from app.kg.loader import load_kg

    kg = load_kg()
    cfg = TransEConfig()
    print(
        f"Training TransE on {len(kg.triples)} triples, "
        f"{len(kg.idx_to_entity)} entities, {len(kg.idx_to_relation)} relations"
    )
    print(f"Config: {asdict(cfg)}")
    E, R, hist = train(kg.triples, len(kg.idx_to_entity), len(kg.idx_to_relation), cfg)
    save(E, R, kg, cfg)
    print(f"Saved to {DEFAULT_ARTIFACTS}")
    print(f"Final loss: {hist[-1]:.4f}")

    # Quick sanity: for a known-positive TREATS edge, is the true tail near the top?
    r_treats = kg.relation_to_idx["TREATS"]
    disease_idxs = np.array([kg.entity_to_idx[d] for d in kg.diseases])
    # imiglucerase TREATS gaucher → head fixed, rank diseases
    h = kg.entity_to_idx["DR:IMIGLUCERASE"]
    ranked, scores = rank_tails(E, R, h, r_treats, disease_idxs)
    gaucher = kg.entity_to_idx["D:GAUCHER"]
    rank = int(np.where(ranked == gaucher)[0][0]) + 1
    print(f"Sanity: Imiglucerase (TREATS) -> ? ranked Gaucher at {rank}/{len(disease_idxs)}")
    top5 = [
        (kg.node_by_id[kg.idx_to_entity[i]]["name"], float(s))
        for i, s in zip(ranked[:5], scores[:5], strict=False)
    ]
    print("  top-5:", top5)

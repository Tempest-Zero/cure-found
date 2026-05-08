"""Pure-NumPy inference for DistMult-scored knowledge-graph embeddings.

R-GCN and CompGCN, as trained by `scripts/train_gnns_pykeen.py`, both
emit per-entity and per-relation embedding tables and use the DistMult
scoring head:

    score(h, r, t) = sum_d  h_d * r_d * t_d

This is the same closed-form trick we use for RotatE: the message-passing
that makes R-GCN / CompGCN expressive happens at *training* time; the
final embeddings are just static tables we score with NumPy at runtime.
That keeps the production container free of PyTorch (saves ~250 MB).

Public surface mirrors `app.ml.rotate` so the repurpose service can swap
between models without per-model branching:

    rank_heads(E, R, r_idx, t_idx, candidate_heads) -> (sorted_ids, sorted_scores)
    rank_tails(E, R, h_idx, r_idx, candidate_tails) -> (sorted_ids, sorted_scores)
    load_for_kg(model_name, kg, artifacts_dir) -> (E, R, meta)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from app.core.paths import ARTIFACTS_DIR as DEFAULT_ARTIFACTS


class ArtifactStaleError(RuntimeError):
    """The DistMult-scored artifact on disk was trained against a different
    KG vocabulary than the one currently loaded. Re-run the Colab GNN
    training notebook (`scripts/colab_gnn_training.ipynb`)."""


def _vocab_digest(idx_to_entity: list[str]) -> str:
    blob = json.dumps(sorted(idx_to_entity), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _distmult_score(
    E: np.ndarray,
    R: np.ndarray,
    h_idx: np.ndarray | int,
    r_idx: int,
    t_idx: np.ndarray | int,
) -> np.ndarray:
    """DistMult: score(h, r, t) = sum_d  h_d * r_d * t_d.

    Vectorises over either h_idx (head ranking) or t_idx (tail ranking)
    when one is a 1-D ndarray of candidate indices.
    """
    h = E[h_idx]
    r = R[r_idx]
    t = E[t_idx]
    if h.ndim == 2:
        return (h * r[None, :] * t[None, :]).sum(axis=-1)
    if t.ndim == 2:
        return (h[None, :] * r[None, :] * t).sum(axis=-1)
    return float((h * r * t).sum())


def rank_heads(
    E: np.ndarray,
    R: np.ndarray,
    r_idx: int,
    t_idx: int,
    candidate_heads: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    scores = _distmult_score(E, R, candidate_heads, r_idx, t_idx)
    order = np.argsort(-scores)
    return candidate_heads[order], scores[order]


def rank_tails(
    E: np.ndarray,
    R: np.ndarray,
    h_idx: int,
    r_idx: int,
    candidate_tails: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    scores = _distmult_score(E, R, h_idx, r_idx, candidate_tails)
    order = np.argsort(-scores)
    return candidate_tails[order], scores[order]


def load(
    model_name: str,
    artifacts_dir: Path = DEFAULT_ARTIFACTS,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Load `<model_name>.npz` + `<model_name>_meta.json`.

    `model_name` must be the lowercase short name used by
    `scripts/train_gnns_pykeen.py` (`rgcn`, `compgcn`).
    """
    npz_path = artifacts_dir / f"{model_name}.npz"
    meta_path = artifacts_dir / f"{model_name}_meta.json"
    with np.load(npz_path, allow_pickle=False) as z:
        E = z["E"].astype(np.float32)
        R = z["R"].astype(np.float32)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return E, R, meta


def load_for_kg(
    model_name: str,
    kg,
    artifacts_dir: Path = DEFAULT_ARTIFACTS,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Load + validate.

    Exact match: artifact vocab == current KG vocab → return as-is.

    Graceful superset: artifact vocab ⊂ current KG vocab (i.e. the KG
    gained new isolated nodes after training, like PW:GSL_BIOSYN) →
    reindex the embedding table to match the current KG's entity order,
    inserting a zero row for each new entity.  This is safe when all new
    entities have degree-0 (no triples), so they are never queried at
    inference time.

    Hard fail: current KG is missing entities the artifact was trained on
    (KG vocabulary shrank), or artifact has no saved digest.
    """
    E, R, meta = load(model_name, artifacts_dir)
    saved = meta.get("entity_vocab_sha256")
    current = _vocab_digest(kg.idx_to_entity)

    if saved is None:
        raise ArtifactStaleError(
            f"{model_name}_meta.json has no entity_vocab_sha256; re-train via "
            "scripts/colab_gnn_training.ipynb."
        )

    if saved == current:
        return E, R, meta

    # Digests differ — check if this is a safe superset case.
    artifact_entities: list[str] = meta.get("idx_to_entity", [])
    if not artifact_entities:
        raise ArtifactStaleError(
            f"{model_name} artifact is stale: saved digest={saved[:12]} "
            f"(n={meta.get('n_entities', '?')}) but current KG digest="
            f"{current[:12]} (n={len(kg.idx_to_entity)}). Re-train."
        )

    artifact_set = set(artifact_entities)
    current_set = set(kg.idx_to_entity)
    new_entities = current_set - artifact_set
    missing_entities = artifact_set - current_set

    if missing_entities:
        # KG lost entities the artifact depends on — cannot recover safely.
        raise ArtifactStaleError(
            f"{model_name} artifact references entities no longer in the KG "
            f"({len(missing_entities)} missing, e.g. {next(iter(missing_entities))}). "
            "Re-train via scripts/colab_gnn_training.ipynb."
        )

    # Safe superset: KG has strictly more entities, artifact has all it needs.
    # Build a reindexed E that matches the current KG entity ordering.
    artifact_idx = {ent: i for i, ent in enumerate(artifact_entities)}
    n_current = len(kg.idx_to_entity)
    E_new = np.zeros((n_current, E.shape[1]), dtype=E.dtype)
    for current_i, ent in enumerate(kg.idx_to_entity):
        art_i = artifact_idx.get(ent)
        if art_i is not None:
            E_new[current_i] = E[art_i]
    # (rows for new_entities remain zero — they are isolated nodes, never queried)

    import logging
    logging.getLogger(__name__).info(
        "distmult.load_for_kg: reindexed %s embeddings: %d artifact entities → "
        "%d current KG entities (%d new isolated nodes padded with zeros)",
        model_name, len(artifact_entities), n_current, len(new_entities),
    )
    return E_new, R, meta

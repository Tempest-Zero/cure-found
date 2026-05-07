"""
RotatE — Knowledge Graph Embedding by Relational Rotation in Complex Space.

Reference: Sun et al., "RotatE: Knowledge Graph Embedding by Relational
Rotation in Complex Space", ICLR 2019.  https://arxiv.org/abs/1902.10197

Why RotatE over TransE
----------------------
TransE (Bordes 2013) treats relations as *translations*: h + r ≈ t.
This fails structurally on three relation patterns present in our KG:

  Antisymmetric:  Drug TREATS Disease  (not vice versa)
      TransE: h+r=t does not enforce h≠t+r — no structural barrier.
      RotatE: h∘r=t but t∘r≠h whenever θ≠0,π.  Enforced by geometry.

  Symmetric:      Gene ASSOCIATED_WITH (bidirectional)
      TransE: forces h+r=t AND t+r=h → r=0, collapsing the embedding.
      RotatE: θ=0 handles symmetry (rotation by 0 = identity) without collapse.

  Compositional:  Gene→ENCODES→Protein→PARTICIPATES_IN→Pathway
      TransE: translations don't compose: (h+r₁)+r₂ = h+(r₁+r₂) by addition,
              which loses the intermediate structure.
      RotatE: rotations compose naturally: θ₁+θ₂ in complex phase space.

Entity embeddings are complex vectors in ℂ^d.
Relation embeddings are phases θ∈ℝ^d; the actual rotation is r=e^(iθ),
which has |r|=1 automatically — no explicit constraint needed.

Training
--------
Loss: sigmoid (negative log-likelihood with fixed-margin γ):
    L = −logσ(γ − d(h,r,t)) − (1/k)·Σⱼ logσ(d(h'ⱼ,r,t'ⱼ) − γ)
where d(h,r,t) = ‖h∘r−t‖₂  (distance in ℂ^d).
Optimizer: Adam (lr=1e-3).  Much more stable than SGD for complex embeddings.

Public interface (identical to app.ml.transe)
---------------------------------------------
    train(triples, n_entities, n_relations, cfg) → (E, R, loss_history)
    rank_heads(E, R, r_idx, t_idx, candidate_heads) → (sorted_idx, scores)
    rank_tails(E, R, h_idx, r_idx, candidate_tails) → (sorted_idx, scores)
    save(E, R, kg, cfg, out_dir)
    load(artifacts_dir) → (E, R, meta)
    load_for_kg(kg, artifacts_dir) → (E, R, meta)

E is a complex64 numpy array of shape [n_entities, dim].
R is a float32 numpy array of shape [n_relations, dim] (phase angles).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from app.core.paths import ARTIFACTS_DIR as DEFAULT_ARTIFACTS

# ---------------------------------------------------------------------------
# Lazy torch import — only load PyTorch when training, not at import time.
# This keeps `import app` cheap for the API server (which only does inference
# from pre-saved numpy artifacts, never trains at runtime).
# ---------------------------------------------------------------------------


def _torch():
    """Return the torch module, raising a clear error if not installed."""
    try:
        import torch

        return torch
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PyTorch is required for RotatE training. Install it with: pip install torch"
        ) from exc


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class RotatEConfig:
    dim: int = 64  # embedding dimension (complex; total real params = 2*dim per entity)
    gamma: float = 6.0  # fixed margin for sigmoid loss; Sun et al. use 6–12
    lr: float = 1e-3  # Adam learning rate
    epochs: int = 1000  # more than TransE — Adam converges differently to SGD
    batch_size: int = 512  # triples per batch; seed KG has 163 → full-batch each epoch
    neg_per_pos: int = 64  # negative samples per positive; more → better gradient signal
    adv_temp: float = 0.5  # self-adversarial temperature (0 = uniform; 0.5 = paper default)
    seed: int = 42


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vocab_digest(idx_to_entity: list[str]) -> str:
    """SHA-256 of the sorted entity vocabulary — same as transe.py."""
    blob = json.dumps(sorted(idx_to_entity), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class ArtifactStaleError(RuntimeError):
    """RotatE artifact on disk was trained against a different KG vocabulary.
    Re-run `python run.py train`."""


# ---------------------------------------------------------------------------
# Numpy inference (no PyTorch needed at runtime)
# ---------------------------------------------------------------------------


def _rotate_distance(
    E: np.ndarray,  # [n_entities, dim] complex64
    R: np.ndarray,  # [n_relations, dim] float32 (phase angles)
    h_idx: np.ndarray | int,
    r_idx: int,
    t_idx: np.ndarray | int,
) -> np.ndarray:
    """RotatE distance ‖h∘r−t‖₂ in complex space.
    Returns negative distance (higher = more likely) to match TransE convention.
    """
    h = E[h_idx]  # [..., dim] complex
    r = np.exp(1j * R[r_idx])  # [dim] complex unit-modulus rotation
    t = E[t_idx]  # [..., dim] complex

    # Broadcast r over batch dimension when h is 2-D
    if h.ndim == 2:
        r = r[None, :]  # [1, dim]
    diff = h * r - t  # [..., dim] complex
    dist = np.sqrt(np.sum(np.abs(diff) ** 2, axis=-1))  # [...] float
    return -dist  # higher = better


def rank_tails(
    E: np.ndarray,
    R: np.ndarray,
    h_idx: int,
    r_idx: int,
    candidate_tails: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Score all candidate tails for (h, r) and return sorted desc by score."""
    scores = _rotate_distance(E, R, h_idx, r_idx, candidate_tails)
    order = np.argsort(-scores)
    return candidate_tails[order], scores[order]


def rank_heads(
    E: np.ndarray,
    R: np.ndarray,
    r_idx: int,
    t_idx: int,
    candidate_heads: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Score all candidate heads for (r, t) and return sorted desc by score.

    Note: for head ranking we compute ‖h∘r−t‖ directly (no inverse relation).
    This matches the TransE head-ranking convention used in eval.py.
    """
    scores = _rotate_distance(E, R, candidate_heads, r_idx, t_idx)
    order = np.argsort(-scores)
    return candidate_heads[order], scores[order]


# ---------------------------------------------------------------------------
# PyTorch model (training only)
# ---------------------------------------------------------------------------


def _build_model(n_entities: int, n_relations: int, cfg: RotatEConfig):
    """Construct and initialise the RotatE nn.Module."""
    torch = _torch()
    import torch.nn as nn

    class RotatEModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            # Entities stored as real vectors of size 2*dim (re‖im concatenated).
            # Relations stored as phase angles θ ∈ ℝ^dim; rotation = e^(iθ).
            self.entity_emb = nn.Embedding(n_entities, 2 * cfg.dim)
            self.relation_phase = nn.Embedding(n_relations, cfg.dim)
            # Initialise: entities ~ Uniform(-1/√dim, 1/√dim); phases ~ Uniform(-π, π)
            bound = 1.0 / (cfg.dim**0.5)
            nn.init.uniform_(self.entity_emb.weight, -bound, bound)
            nn.init.uniform_(self.relation_phase.weight, -torch.pi, torch.pi)

        # ---- scoring ---- #

        def _score(self, h_idx, r_idx, t_idx):
            """Return −‖h∘r−t‖₂.  Shape: [B] (higher = more plausible)."""
            d = cfg.dim
            h = self.entity_emb(h_idx)  # [B, 2d]
            t = self.entity_emb(t_idx)  # [B, 2d]
            theta = self.relation_phase(r_idx)  # [B, d]

            h_re, h_im = h[:, :d], h[:, d:]
            t_re, t_im = t[:, :d], t[:, d:]
            r_re = torch.cos(theta)  # [B, d]
            r_im = torch.sin(theta)  # [B, d]

            # Element-wise complex multiplication: h ∘ r
            rot_re = h_re * r_re - h_im * r_im
            rot_im = h_re * r_im + h_im * r_re

            diff_re = rot_re - t_re
            diff_im = rot_im - t_im
            # Distance in ℂ^d: sqrt(Σ |diff_i|²)
            dist = torch.sqrt((diff_re**2 + diff_im**2).sum(dim=-1) + 1e-9)  # [B]
            return -dist  # higher = better

        # ---- loss ---- #

        def forward(self, pos_h, pos_r, pos_t, neg_h, neg_r, neg_t):
            """Self-adversarial negative sampling loss (Sun et al. Eq. 4–5).

            pos_*: [B]    — positive triple indices
            neg_*: [B*K]  — negative triple indices (K negatives per positive)
            """
            import torch.nn.functional as F

            K = cfg.neg_per_pos
            B = pos_h.shape[0]

            # Repeat positives K times to pair with their negatives
            pos_h_r = pos_h.repeat_interleave(K)  # [B*K]
            pos_r_r = pos_r.repeat_interleave(K)
            pos_t_r = pos_t.repeat_interleave(K)

            pos_score = self._score(pos_h_r, pos_r_r, pos_t_r)  # [B*K]
            neg_score = self._score(neg_h, neg_r, neg_t)  # [B*K]

            # Convert score (= -distance) to distances for the loss
            pos_dist = -pos_score  # [B*K]
            neg_dist = -neg_score  # [B*K]

            pos_loss = -F.logsigmoid(cfg.gamma - pos_dist)  # push pos close

            if cfg.adv_temp > 0.0:
                # Self-adversarial weighting: weight negatives by softmax over
                # their current score (harder negatives get more gradient weight).
                # Reshape to [B, K] for per-positive softmax, then flatten back.
                neg_score_bk = neg_score.view(B, K)
                weights = torch.softmax(neg_score_bk * cfg.adv_temp, dim=-1)  # [B, K]
                neg_loss_bk = -F.logsigmoid(neg_dist.view(B, K) - cfg.gamma)  # [B, K]
                neg_loss = (weights.detach() * neg_loss_bk).sum(dim=-1)  # [B]
                return pos_loss.view(B, K).mean(dim=-1).mean() + neg_loss.mean()
            else:
                neg_loss = -F.logsigmoid(neg_dist - cfg.gamma)
                return pos_loss.mean() + neg_loss.mean()

    return RotatEModel()


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train(
    triples: list[tuple[int, int, int]],
    n_entities: int,
    n_relations: int,
    cfg: RotatEConfig | None = None,
    verbose: bool = True,
) -> tuple[np.ndarray, np.ndarray, list[float]]:
    """Train RotatE on `triples`.

    Returns
    -------
    E : np.ndarray, complex64, shape [n_entities, dim]
        Complex entity embeddings (real‖imag parts merged into complex dtype).
    R : np.ndarray, float32, shape [n_relations, dim]
        Relation phase angles θ (the actual rotation is e^(iθ)).
    loss_history : list[float]
        Mean loss per epoch.
    """
    torch = _torch()

    cfg = cfg or RotatEConfig()
    rng = torch.Generator()
    rng.manual_seed(cfg.seed)

    model = _build_model(n_entities, n_relations, cfg)
    optimizer = torch.optim.Adam(model.parameters(), lr=cfg.lr)

    T = torch.tensor(triples, dtype=torch.long)  # [n_triples, 3]
    n_triples = T.shape[0]

    # Precompute truth sets for best-effort negative filtering
    rh_to_t: dict[tuple[int, int], set[int]] = {}
    rt_to_h: dict[tuple[int, int], set[int]] = {}
    for h, r, t in triples:
        rh_to_t.setdefault((r, h), set()).add(t)
        rt_to_h.setdefault((r, t), set()).add(h)

    loss_history: list[float] = []
    t0 = time.time()

    for epoch in range(cfg.epochs):
        model.train()
        perm = torch.randperm(n_triples, generator=rng)
        T_shuf = T[perm]

        epoch_loss = 0.0
        n_batches = 0

        for start in range(0, n_triples, cfg.batch_size):
            batch = T_shuf[start : start + cfg.batch_size]
            bsz = batch.shape[0]
            pos_h, pos_r, pos_t = batch[:, 0], batch[:, 1], batch[:, 2]

            K = cfg.neg_per_pos
            total = bsz * K

            # Sample negatives — corrupt head or tail with equal probability
            corrupt_tail = torch.rand(total, generator=rng) < 0.5
            neg_ents = torch.randint(0, n_entities, (total,), generator=rng)

            neg_h = pos_h.repeat_interleave(K)  # [total]
            neg_r = pos_r.repeat_interleave(K)
            neg_t = pos_t.repeat_interleave(K)

            # Substitute the corrupted side
            neg_h = torch.where(~corrupt_tail, neg_ents, neg_h)
            neg_t = torch.where(corrupt_tail, neg_ents, neg_t)

            # Best-effort filter: resample if we accidentally generated a true triple
            neg_h_np = neg_h.numpy()
            neg_r_np = neg_r.numpy()
            neg_t_np = neg_t.numpy()
            for i in range(total):
                ri, hi, ti = int(neg_r_np[i]), int(neg_h_np[i]), int(neg_t_np[i])
                if corrupt_tail[i]:
                    if ti in rh_to_t.get((ri, hi), ()):
                        neg_t_np[i] = (ti + 1) % n_entities
                else:
                    if hi in rt_to_h.get((ri, ti), ()):
                        neg_h_np[i] = (hi + 1) % n_entities
            neg_h = torch.from_numpy(neg_h_np)
            neg_t = torch.from_numpy(neg_t_np)

            optimizer.zero_grad()
            loss = model(pos_h, pos_r, pos_t, neg_h, neg_r, neg_t)
            loss.backward()
            # Gradient clipping — helps with the complex rotation landscape
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            epoch_loss += float(loss.item())
            n_batches += 1

        mean_loss = epoch_loss / max(n_batches, 1)
        loss_history.append(mean_loss)

        if verbose and (epoch % max(cfg.epochs // 20, 1) == 0 or epoch == cfg.epochs - 1):
            print(
                f"  epoch {epoch + 1:4d}/{cfg.epochs}  loss={mean_loss:.4f}  "
                f"({time.time() - t0:.1f}s)",
                flush=True,
            )

    # Extract numpy artifacts from the trained model
    with torch.no_grad():
        dim = cfg.dim
        ew = model.entity_emb.weight.cpu().numpy()  # [n_entities, 2*dim]
        E_complex = (ew[:, :dim] + 1j * ew[:, dim:]).astype(np.complex64)
        R_phase = model.relation_phase.weight.cpu().numpy().astype(np.float32)

    return E_complex, R_phase, loss_history


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------


def save(
    E: np.ndarray,
    R: np.ndarray,
    kg,
    cfg: RotatEConfig,
    out_dir: Path = DEFAULT_ARTIFACTS,
) -> None:
    """Persist RotatE artifacts to `out_dir/rotate.npz` + `kge_meta.json`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez(out_dir / "rotate.npz", E=E, R=R)
    (out_dir / "kge_meta.json").write_text(
        json.dumps(
            {
                "model": "RotatE",
                "paper": "Sun et al., ICLR 2019",
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
    """Load RotatE artifacts. Returns (E_complex, R_phase, meta)."""
    with np.load(artifacts_dir / "rotate.npz", allow_pickle=False) as z:
        E = z["E"].astype(np.complex64)  # [n_entities, dim]
        R = z["R"].astype(np.float32)  # [n_relations, dim]
    meta = json.loads((artifacts_dir / "kge_meta.json").read_text(encoding="utf-8"))
    return E, R, meta


def load_for_kg(kg, artifacts_dir: Path = DEFAULT_ARTIFACTS) -> tuple[np.ndarray, np.ndarray, dict]:
    """Load + validate. Raises ArtifactStaleError if vocab has changed."""
    E, R, meta = load(artifacts_dir)
    saved = meta.get("entity_vocab_sha256")
    current = _vocab_digest(kg.idx_to_entity)
    if saved is None:
        if meta.get("idx_to_entity") != kg.idx_to_entity:
            raise ArtifactStaleError(
                "RotatE artifact has no entity_vocab_sha256 and its "
                "idx_to_entity does not match the current KG. "
                "Run `python run.py train`."
            )
        return E, R, meta
    if saved != current:
        saved_n = meta.get("n_entities", "?")
        raise ArtifactStaleError(
            f"RotatE artifact is stale: saved digest={saved[:12]} (n={saved_n}) "
            f"but current KG digest={current[:12]} (n={len(kg.idx_to_entity)}). "
            "Re-run `python run.py train`."
        )
    return E, R, meta


# ---------------------------------------------------------------------------
# Entry point (python -m app.ml.rotate)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from app.kg.loader import load_kg

    kg = load_kg()
    cfg = RotatEConfig()
    print(
        f"Training RotatE on {len(kg.triples)} triples, "
        f"{len(kg.idx_to_entity)} entities, {len(kg.idx_to_relation)} relations"
    )
    print(f"Config: {asdict(cfg)}")
    E, R, hist = train(kg.triples, len(kg.idx_to_entity), len(kg.idx_to_relation), cfg)
    save(E, R, kg, cfg)
    print(f"Saved to {DEFAULT_ARTIFACTS}")
    print(f"Final loss: {hist[-1]:.4f}")

    # Sanity: imiglucerase TREATS gaucher — should rank Gaucher near the top
    r_treats = kg.relation_to_idx["TREATS"]
    disease_idxs = np.array([kg.entity_to_idx[d] for d in kg.diseases])
    h = kg.entity_to_idx["DR:IMIGLUCERASE"]
    ranked, scores = rank_tails(E, R, h, r_treats, disease_idxs)
    gaucher = kg.entity_to_idx["D:GAUCHER"]
    rank = int(np.where(ranked == gaucher)[0][0]) + 1
    print(f"Sanity: Imiglucerase -> ? ranked Gaucher at {rank}/{len(disease_idxs)}")
    top5 = [
        (kg.node_by_id[kg.idx_to_entity[i]]["name"], float(s))
        for i, s in zip(ranked[:5], scores[:5], strict=False)
    ]
    print("  top-5:", top5)

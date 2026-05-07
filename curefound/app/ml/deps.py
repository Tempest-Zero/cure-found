"""Annotated-Depends alias for the KGE (RotatE) artefacts.

Rarely needed -- the repurpose service captures (E, R) at construction
time so per-request deps are not required on the hot path. Exposed here
for Phase 1+ tooling that wants to load artifacts without instantiating
the whole service (e.g. admin routes that re-rank on-the-fly).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

import numpy as np
from fastapi import Depends, Request


@dataclass
class KGEArtifacts:
    """RotatE knowledge-graph-embedding artefacts.

    `E` is a complex64 array of shape [n_entities, dim] — entity embeddings
    in ℂ^d.  `R` is a float32 array of shape [n_relations, dim] — relation
    phase angles θ; the actual rotation in complex space is e^(iθ).
    """

    E: np.ndarray
    R: np.ndarray
    meta: dict[str, Any]


def get_kge_artifacts(request: Request) -> KGEArtifacts:
    E = request.app.state.kge_E
    R = request.app.state.kge_R
    meta = request.app.state.kge_meta
    return KGEArtifacts(E=E, R=R, meta=meta)


KGEDep = Annotated[KGEArtifacts, Depends(get_kge_artifacts)]

"""Annotated-Depends alias for the TransE artefacts.

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
class TransEArtifacts:
    E: np.ndarray
    R: np.ndarray
    meta: dict[str, Any]


def get_transe_artifacts(request: Request) -> TransEArtifacts:
    E = request.app.state.transe_E
    R = request.app.state.transe_R
    meta = request.app.state.transe_meta
    return TransEArtifacts(E=E, R=R, meta=meta)


TransEDep = Annotated[TransEArtifacts, Depends(get_transe_artifacts)]

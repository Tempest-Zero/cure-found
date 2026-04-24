"""Project-root + canonical-path resolution.

One place that knows where the `curefound/` project root lives on disk.
Every other module imports `PROJECT_ROOT` (or one of the derived paths)
instead of doing its own `Path(__file__).resolve().parents[N]` walk.

Why centralise this: the hardened MVP had three independent walks --
`ROOT = Path(__file__).resolve().parents[1]` in `kg/loader.py`,
`api/main.py`, and `ml/transe.py`. After the refactor, each file's depth
relative to the project root differs (`app/kg/loader.py` needs `parents[2]`,
`app/main.py` needs `parents[1]`, etc). Centralising here means the walk
is written once and Settings reads from here instead of each module
hard-coding.
"""

from __future__ import annotations

from pathlib import Path

# `app/core/paths.py` -> `app/core/` -> `app/` -> project root
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# Default data-layout paths. `Settings` can override any of these via .env;
# treat these as the "where things live if .env says nothing" defaults.
DATA_DIR: Path = PROJECT_ROOT / "data"
SEED_DIR: Path = DATA_DIR / "seed"
SEED_KG_PATH: Path = SEED_DIR / "kg.json"
ARTIFACTS_DIR: Path = DATA_DIR / "artifacts"
RAW_DIR: Path = DATA_DIR / "raw"

# Static frontend (the MVP's single-page Cytoscape demo) and Phase 6 build
# output. `app.main` mounts these when they exist on disk; missing
# directories are not an error.
FRONTEND_DIR: Path = PROJECT_ROOT / "frontend"
FRONTEND_INDEX: Path = FRONTEND_DIR / "index.html"


def resolve_project_path(raw: str | Path | None, default: Path) -> Path:
    """Resolve an optional config path against the project root.

    - `None` or empty -> return `default`
    - absolute path   -> return as-is
    - relative path   -> anchor at `PROJECT_ROOT`

    Lets `.env` say `DATA_DIR=data` (which would otherwise resolve against
    the current working directory and break `docker run` vs `cd && python`).
    """
    if raw is None or raw == "":
        return default
    p = Path(raw)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p

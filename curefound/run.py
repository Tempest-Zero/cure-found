"""
Cross-platform task runner. For Windows users without GNU make.

Usage:
    python run.py train   # train RotatE on the current seed KG (~20 min CPU)
    python run.py eval    # leave-one-out eval w/ bootstrap CIs (~2 hr CPU)
    python run.py serve   # start FastAPI on :8000 with --reload
    python run.py smoke   # end-to-end demo flow checks
    python run.py expand  # apply HPO HPOA expansion to data/seed/kg-mvp.json
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(cmd: list[str]) -> int:
    print(">", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    task = argv[0]
    if task == "train":
        return run([sys.executable, "-m", "app.ml.rotate"])
    if task == "eval":
        # Pass through any extra args, e.g. `python run.py eval --epochs 300`
        return run([sys.executable, "-m", "app.ml.eval", *argv[1:]])
    if task == "serve":
        port = argv[1] if len(argv) > 1 else "8000"
        return run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                port,
                "--reload",
            ]
        )
    if task == "smoke":
        return run([sys.executable, "-m", "tests.e2e.smoke"])
    if task == "expand":
        return run([sys.executable, "-m", "app.etl.expand_hpo_lsd", *argv[1:]])
    print(f"unknown task: {task}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

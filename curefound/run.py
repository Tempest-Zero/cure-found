"""
Cross-platform runner. For Windows users without GNU make.

Usage:
    python run.py seed    # regenerate data/seed/kg.json
    python run.py train   # train TransE
    python run.py eval    # evaluate TransE (outputs data/artifacts/eval_report.json)
    python run.py serve   # start FastAPI
    python run.py smoke   # end-to-end smoke test
    python run.py all     # seed + train
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
    if task == "seed":
        return run([sys.executable, "-m", "app.etl.build_seed_kg"])
    if task == "train":
        return run([sys.executable, "-m", "app.ml.transe"])
    if task == "eval":
        return run([sys.executable, "-m", "app.ml.eval"])
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
    if task == "all":
        rc = run([sys.executable, "-m", "app.etl.build_seed_kg"])
        if rc:
            return rc
        return run([sys.executable, "-m", "app.ml.transe"])
    print(f"unknown task: {task}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

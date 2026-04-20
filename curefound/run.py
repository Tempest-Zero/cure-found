"""
Cross-platform runner. For Windows users without GNU make.

Usage:
    python run.py seed    # regenerate seed KG
    python run.py train   # train TransE
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
        return run([sys.executable, "etl/build_seed_kg.py"])
    if task == "train":
        return run([sys.executable, "ml/transe.py"])
    if task == "serve":
        port = argv[1] if len(argv) > 1 else "8000"
        return run([sys.executable, "-m", "uvicorn", "api.main:app",
                    "--host", "0.0.0.0", "--port", port, "--reload"])
    if task == "smoke":
        return run([sys.executable, "tests/smoke.py"])
    if task == "all":
        rc = run([sys.executable, "etl/build_seed_kg.py"])
        if rc: return rc
        return run([sys.executable, "ml/transe.py"])
    print(f"unknown task: {task}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

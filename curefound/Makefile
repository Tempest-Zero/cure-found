# CureFound -- task runner. Works with GNU make (Git Bash / WSL).
# Windows users: `python run.py <task>` is the cross-platform equivalent.

PY := python
PORT ?= 8000

.PHONY: train eval serve smoke expand lint test help

help:
	@echo "CureFound tasks:"
	@echo "  make train   -- train RotatE, save artifacts to data/artifacts/"
	@echo "  make eval    -- evaluate RotatE (LOO + bootstrap CI -> eval_report.json)"
	@echo "  make serve   -- run FastAPI on PORT=$(PORT)  (browse http://localhost:$(PORT)/)"
	@echo "  make smoke   -- end-to-end smoke test (TestClient, no server)"
	@echo "  make expand  -- apply HPO HPOA expansion (kg-mvp.json -> kg.json)"
	@echo "  make lint    -- run ruff check + format check"
	@echo "  make test    -- run full pytest suite"

train:
	$(PY) -m app.ml.rotate

eval:
	$(PY) -m app.ml.eval

serve:
	$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --reload

smoke:
	$(PY) -m tests.e2e.smoke

expand:
	$(PY) -m app.etl.expand_hpo_lsd

lint:
	$(PY) -m ruff check app tests
	$(PY) -m ruff format --check app tests

test:
	$(PY) -m pytest tests/regression tests/unit -q

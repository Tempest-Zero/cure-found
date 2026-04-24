# CureFound — task runner. Works with GNU make (Git Bash / WSL).
# Windows users: `python run.py <task>` is the cross-platform equivalent.

PY := python
PORT ?= 8000

.PHONY: all seed train eval serve smoke lint test clean help

help:
	@echo "CureFound tasks:"
	@echo "  make seed    — regenerate data/seed/kg.json"
	@echo "  make train   — train TransE, save artifacts to data/artifacts/"
	@echo "  make eval    — evaluate TransE (outputs data/artifacts/eval_report.json)"
	@echo "  make serve   — run FastAPI on PORT=$(PORT)  (browse http://localhost:$(PORT)/)"
	@echo "  make smoke   — end-to-end smoke test (TestClient, no server)"
	@echo "  make lint    — run ruff check + format check"
	@echo "  make test    — run full pytest suite"
	@echo "  make all     — seed + train"
	@echo "  make clean   — remove generated data/ artifacts"

all: seed train

seed:
	$(PY) -m app.etl.build_seed_kg

train:
	$(PY) -m app.ml.transe

eval:
	$(PY) -m app.ml.eval

serve:
	$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --reload

smoke:
	$(PY) -m tests.e2e.smoke

lint:
	$(PY) -m ruff check app tests
	$(PY) -m ruff format --check app tests

test:
	$(PY) -m pytest tests/ -v

clean:
	rm -rf data/seed data/artifacts

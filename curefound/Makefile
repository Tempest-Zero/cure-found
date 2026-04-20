# CureFound MVP — simple task runner. Works with GNU make (Git Bash / WSL).
# Windows cmd users can read the commands and run them manually.

PY := python
PORT ?= 8000

.PHONY: all seed train serve smoke clean help

help:
	@echo "CureFound MVP tasks:"
	@echo "  make seed    — regenerate data/seed/kg.json"
	@echo "  make train   — train TransE, save artifacts to data/artifacts/"
	@echo "  make serve   — run FastAPI on PORT=$(PORT)  (browse http://localhost:$(PORT)/)"
	@echo "  make smoke   — end-to-end smoke test (TestClient, no server)"
	@echo "  make all     — seed + train"
	@echo "  make clean   — remove generated data/ artifacts"

all: seed train

seed:
	$(PY) etl/build_seed_kg.py

train:
	$(PY) ml/transe.py

serve:
	$(PY) -m uvicorn api.main:app --host 0.0.0.0 --port $(PORT) --reload

smoke:
	$(PY) tests/smoke.py

clean:
	rm -rf data/seed data/artifacts

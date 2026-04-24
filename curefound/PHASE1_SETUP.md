# Phase 1 Setup Guide

> **Audience**: reviewers evaluating the FYP, and collaborators cloning the
> repo for the first time. Covers everything from clone to running demo in
> under 10 minutes.

---

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.11+ | Runtime for FastAPI + TransE |
| Docker Desktop | 4.x (AMD64 / ARM64) | Neo4j service container |
| Git | any | Clone + history |
| 8 GB RAM free | — | Neo4j JVM heap (2 G) + Python process |
| 50 GB disk free | — | PrimeKG raw download (~4 GB) + Neo4j data |

Verify Docker is running before proceeding:
```bash
docker run --rm hello-world
```

---

## 1. Clone and install

```bash
git clone <repo-url> curefound
cd curefound

# Create a virtual environment (Python 3.11+)
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# Install runtime + dev dependencies
pip install -e ".[dev]"
```

---

## 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and change at minimum:

```
NEO4J_PASSWORD=<your-own-password>   # anything except "changethis_dev_only"
```

Everything else can stay at the defaults for a local demo run.

---

## 3. Start Neo4j

```bash
docker compose up -d neo4j
```

The container exposes:
- **Bolt** `bolt://localhost:7687` — used by the backend
- **Browser** `http://localhost:7474` — UI for exploring the graph directly

Wait for the healthcheck to pass (~30 s on first boot):
```bash
docker compose ps   # State should show "(healthy)"
```

---

## 4. Run the MVP (NetworkX backend, no Neo4j required)

The Phase 0 hardened MVP uses an in-memory NetworkX graph loaded from
`data/seed/kg.json`. This requires **no Neo4j** and is the fastest way to
verify the codebase.

```bash
python run.py serve     # starts uvicorn on http://localhost:8000
```

Open `http://localhost:8000` in a browser — the Cytoscape.js UI loads.

To run the full end-to-end smoke test (17 checks):
```bash
python run.py smoke
```

---

## 5. Phase 1 data ingest (Neo4j backend)

> **Note**: Phase 1 ingestors land after the structural refactor. This
> section documents the expected flow; the commands become active once
> `app/etl/fetch_all.py` and the per-source ingestors are merged.

### 5a. Download source data

```bash
python -m app.etl.fetch_all
```

Downloads PrimeKG, DrugCentral, HPO, Orphanet, and Reactome into
`data/raw/`. Sources that require a browser login are documented with
manual-download instructions in `app/etl/fetch_all.py`.

Expected sizes:

| Source | Raw size |
|---|---|
| PrimeKG | ~4 GB (Harvard Dataverse) |
| DrugCentral | ~200 MB |
| HPO | ~15 MB |
| Orphanet | ~50 MB |
| Reactome | ~30 MB |

### 5b. Run ingestors

```bash
python -m app.etl.ingest.all
```

This applies each ingestor in dependency order and writes the resulting
graph into Neo4j using Bolt. Progress bars show node/edge counts per source.

### 5c. Verify ingest

```bash
# Switch the app to the Neo4j backend:
# In .env set:  KG_BACKEND=neo4j

python run.py smoke   # all 17 checks must still pass
```

---

## 6. Re-train TransE (optional)

If you changed the KG graph (new ingest run), re-train:

```bash
python run.py train   # ~5 minutes on CPU; ~1 minute on CUDA
python run.py eval    # prints MRR / Hits@10, writes eval_report.json
```

---

## 7. Full Docker stack (Phase 1 Step 5)

Once `docker/Dockerfile.backend` is finalised and the backend service is
uncommented in `compose.yml`:

```bash
docker compose up          # starts neo4j + backend
# Open http://localhost:8000
```

---

## Key endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check |
| `GET /stats` | KG node / edge counts |
| `GET /search?q=...` | Entity fuzzy search |
| `GET /node/{id}` | Node detail + xrefs |
| `POST /repurpose` | TransE + graph repurposing for a disease |
| `POST /diagnose` | HPO-symptom → disease scoring |
| `GET /subgraph?node_id=...` | BFS subgraph for Cytoscape visualisation |
| `GET /docs` | OpenAPI UI (local only) |

---

## Troubleshooting

**`KG not loaded on app.state`** — the `lifespan` context manager didn't fire.
Make sure you are using `with TestClient(app) as c:` in tests, or start the
server via `python run.py serve` (not by importing `app` directly).

**`ArtifactStaleError`** — the TransE `.npz` in `data/artifacts/` was trained
against a different KG vocabulary. Re-run `python run.py train` to regenerate.

**`docker compose up neo4j` stuck** — Neo4j can take 60–90 s on first boot
while it initialises the store. Watch logs with `docker compose logs -f neo4j`.

**Port 7687 already in use** — another Neo4j instance is running locally.
Stop it or change the port mapping in `compose.yml` (`"7688:7687"`).

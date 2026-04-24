# CureFound

**Status: pre-Phase-1 refactor complete.** 99-node seed KG · TransE embeddings ·
FastAPI + Cytoscape.js UI · Docker scaffolding · five Phase-1 ingestors written ·
Neo4j backend implemented · 88 tests (23 regression + 65 integration) + 17 smoke
checks, all green.

> ⚠ **Research prototype. Not for clinical use.**

---

## What it does

Two demo flows, both working end-to-end against the 99-node seed KG:

1. **Drug repurposing.** Given a rare disease (e.g. Niemann-Pick C), rank drug
   candidates most likely to treat it. Hybrid ranker: TransE link-prediction
   `(drug, TREATS, disease)` + Jaccard pathway-neighborhood overlap + Reciprocal
   Rank Fusion. Returns evidence paths per candidate for explainability.

2. **Symptom-based diagnosis.** Given HPO phenotype terms (e.g. cherry-red spot +
   hypotonia + seizures), rank candidate diseases. Hybrid ranker: Jaccard symptom
   overlap + IDF-weighted match + RRF. Unresolvable input tokens are reported
   explicitly rather than silently dropped.

Plus a free-form **KG explorer**: search any node, view its k-hop subgraph as an
interactive Cytoscape.js graph.

---

## Quickstart — MVP (no Neo4j, no Docker)

```bash
cd curefound

# Install (editable + dev tools)
pip install -e ".[dev]"

# 1. Build the seed KG  (-> data/seed/kg.json)
python run.py seed

# 2. Train TransE       (-> data/artifacts/, ~6 s)
python run.py train

# 3. Serve
python run.py serve
# http://localhost:8000/       interactive UI
# http://localhost:8000/docs   OpenAPI / Swagger
```

End-to-end smoke test (17 checks, no server needed):

```bash
python run.py smoke
```

Full test suite (88 tests):

```bash
pytest tests/regression tests/integration -v
```

---

## Quickstart — Phase 1 (Neo4j + full KG ingest)

See **[PHASE1_SETUP.md](PHASE1_SETUP.md)** for the complete walkthrough. Short version:

```bash
# 1. Copy and edit .env
cp .env.example .env
# Set NEO4J_PASSWORD, DATAVERSE_API_TOKEN (for PrimeKG), etc.

# 2. Start Neo4j
docker compose up -d neo4j

# 3. Download raw data (~5 GB: PrimeKG, DrugCentral, HPO, Orphanet, Reactome)
python -m app.etl.fetch_all

# 4. Run ingestors and load into Neo4j
python -m app.etl.ingest.all --target neo4j

# 5. Train TransE on the full KG
python run.py train

# 6. Serve against Neo4j
KG_BACKEND=neo4j python run.py serve
```

---

## Architecture

```
curefound/
├── app/                            Python package
│   ├── main.py                     create_app() factory + module-level app
│   ├── core/
│   │   ├── config.py               Settings(BaseSettings) — reads .env
│   │   ├── logging.py              structlog + asgi-correlation-id
│   │   ├── exceptions.py           AppError hierarchy + FastAPI handlers
│   │   ├── lifespan.py             startup/shutdown: load KG + TransE
│   │   └── paths.py                project-root resolution
│   ├── kg/
│   │   ├── loader.py               NetworkX KG (seed / networkx backend)
│   │   ├── neo4j_backend.py        Neo4j 5 Bolt backend (same Protocol)
│   │   ├── backend.py              KGBackend runtime_checkable Protocol
│   │   ├── router.py               /stats /search /node /subgraph
│   │   ├── schemas.py              NodeBrief, NodeDetail, SubgraphResponse
│   │   └── deps.py                 KGDep = Annotated[KG, Depends(get_kg)]
│   ├── repurpose/
│   │   ├── service.py              TransE + Jaccard + RRF pipeline
│   │   ├── router.py               POST /repurpose
│   │   ├── schemas.py              RepurposeRequest/Response/Candidate
│   │   └── deps.py                 RepurposeDep
│   ├── diagnose/
│   │   ├── service.py              Jaccard + IDF + RRF pipeline
│   │   ├── router.py               POST /diagnose
│   │   ├── schemas.py              DiagnoseRequest/Response/Candidate
│   │   └── deps.py                 DiagnoseDep
│   ├── admin/
│   │   ├── router.py               GET /health
│   │   └── schemas.py              HealthResponse
│   ├── ml/
│   │   ├── transe.py               Pure-NumPy TransE trainer + evaluator
│   │   └── eval.py                 Leave-one-out filtered evaluation
│   └── etl/
│       ├── build_seed_kg.py        Hand-curated 99-node LSD seed KG
│       ├── id_map_service.py       xref → canonical-id resolver
│       ├── fetch_all.py            Download orchestrator (Phase 1)
│       ├── _base.py                Ingestor ABC + KGAccumulator
│       └── ingest/
│           ├── primekg.py          PrimeKG backbone (LSD-scope filter)
│           ├── drugcentral.py      Authoritative TREATS + approval_year
│           ├── hpo.py              HPO DAG + HPOA disease-phenotype
│           ├── orphanet.py         Orphanet rare-disease registry
│           ├── reactome.py         Homo sapiens pathways
│           └── all.py              Pipeline runner (--target json|neo4j)
├── tests/
│   ├── conftest.py                 Shared fixtures: test_app, sync/async client
│   ├── regression/
│   │   └── test_backend.py         23 pins — one per named defect (C1-C5, H1-H7, M1-M4)
│   ├── integration/
│   │   ├── conftest.py             int_client respects KG_BACKEND env var
│   │   ├── test_admin_router.py    /health + dual-mount parity
│   │   ├── test_kg_router.py       /stats /search /node /subgraph (31 tests)
│   │   ├── test_repurpose_router.py POST /repurpose (15 tests)
│   │   └── test_diagnose_router.py POST /diagnose (14 tests)
│   └── e2e/
│       └── smoke.py                17 end-to-end checks (python run.py smoke)
├── frontend/
│   ├── index.html                  Single-page Cytoscape.js UI (3 tabs)
│   ├── style.css
│   └── app.js
├── data/
│   ├── seed/kg.json                99 nodes · 163 edges (generated)
│   ├── artifacts/                  TransE weights + metadata (generated)
│   └── raw/                        .gitignored; fetch_all.py target
├── docker/
│   ├── Dockerfile.backend          Multi-stage Python 3.11-slim
│   └── neo4j/init.cypher           Constraints + indexes + FTS index
├── scripts/
│   ├── dev.sh                      Local dev wrapper
│   └── lint.sh                     ruff check --fix + ruff format
├── compose.yml                     Neo4j 5 service + (commented) backend
├── .env.example                    All Settings fields documented
├── pyproject.toml                  Deps + Ruff + pytest config
├── run.py                          Cross-platform task runner
└── PHASE1_SETUP.md                 Phase 1 detailed setup guide
```

---

## API reference

Both the bare path (`/health`) and the versioned prefix (`/api/v1/health`) work —
dual-mount for backward compatibility with the existing frontend.

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health` | Liveness + KG version + backend name |
| GET  | `/stats`  | Entity / relation / edge counts by type |
| GET  | `/search?q=&type=&limit=` | Substring search with optional type filter |
| GET  | `/node/{node_id}` | Node detail + xrefs + in/out degree |
| GET  | `/subgraph?node_id=&k=&max_nodes=` | Cytoscape-ready k-hop subgraph |
| POST | `/repurpose` | Ranked drug candidates with evidence paths |
| POST | `/diagnose`  | Ranked disease candidates from HPO symptom ids |

Live OpenAPI: `GET /docs` (local environment only).

### Quick examples

```bash
# Repurposing for Niemann-Pick C (canonical or MONDO id both work)
curl -X POST http://localhost:8000/repurpose \
  -H "Content-Type: application/json" \
  -d '{"disease_id": "D:NPC", "top_k": 5, "include_already_approved": false}'

curl -X POST http://localhost:8000/repurpose \
  -H "Content-Type: application/json" \
  -d '{"disease_id": "MONDO:0009937", "top_k": 5}'

# Diagnose from HPO ids
curl -X POST http://localhost:8000/diagnose \
  -H "Content-Type: application/json" \
  -d '{"symptoms": ["HP:0010729","HP:0001252","HP:0001263","HP:0001250"], "top_k": 5}'

# KG stats
curl http://localhost:8000/stats
```

---

## Seed KG (MVP baseline)

```
99 entities · 7 relations · 163 triples
  Disease: 13   Gene: 13   Protein: 16
  Drug:    19   Pathway: 12   Symptom: 26

  CAUSES: 14    ENCODES: 13   TARGETS: 19
  TREATS: 16    HAS_PHENOTYPE: 68
  PARTICIPATES_IN: 31   ASSOCIATED_WITH: 2
```

Focus: **Lysosomal Storage Disorders** (Gaucher, Fabry, Niemann-Pick A/B/C, Pompe,
Tay-Sachs, Krabbe, MPS-I/II, MLD) + Cystic Fibrosis and Huntington as non-LSD
controls.

---

## Held-out evaluation

`python run.py eval` runs the Bordes-2013 / PyKEEN leave-one-out filtered protocol:
retrain TransE on N-1 `TREATS` triples, rank every Drug for each held-out tail,
filter known-true heads before ranking.  Report written to
`data/artifacts/eval_report.json`.

**Seed KG · 16 held-out TREATS · 19 Drug candidates · TransE dim=64 · 800 epochs:**

| Metric | Value |
|---|---|
| Mean rank (filtered) | **9.88 / 19** |
| MRR (filtered) | **0.131** |
| Hits@1 | **0.000** |
| Hits@3 | **0.062** |
| Hits@10 | **0.562** |

These numbers are the *honest baseline* for the thesis.  TransE on a 99-node graph
with 16 training signals is expected to be weak.  The hybrid ranker (TransE + Jaccard
pathway score + RRF) still surfaces correct LSD candidates because the graph-score
carries most of the signal at this graph scale. Phase 2 will replace this with a
PyKEEN pipeline (RotatE + CompGCN) on the full PrimeKG-derived graph and reproduce
the Hetionet baseline for comparison.

**Known candidates surfaced by the hybrid ranker (top-10, not in the TREATS graph):**

- **Hydroxypropyl-β-cyclodextrin** for Niemann-Pick C (clinical trial stage)
- **Ambroxol** for Gaucher (chaperone candidate)
- **Vorinostat / Rapamycin** mid-table for LSDs via autophagy / HDAC pathways

### Diagnostic accuracy on hand-picked LSD profiles

| Input symptoms | Top-1 predicted | Correct? |
|---|---|---|
| splenomegaly + anemia + bone pain + hepatomegaly + thrombocytopenia | **Gaucher** | ✅ |
| angiokeratoma + renal + neuropathy + cardiomyopathy | **Fabry** | ✅ |
| hepatomegaly + splenomegaly + VSGP + ataxia + seizures + devdelay | **Niemann-Pick C** | ✅ |
| cherry-red spot + hypotonia + devdelay + seizures | **Tay-Sachs** | ✅ |

Pinned as integration-test assertions in `tests/integration/test_diagnose_router.py`
and as smoke checks in `tests/e2e/smoke.py`.

---

## Scoring semantics

All scores exposed by the API carry `description=` in the OpenAPI schema.  Summary:

**Repurposing (`/repurpose`)**

- `model_score` — TransE: `-||h + r - t||₂`. Higher is better. Not comparable
  across retrains (embedding space is rotation-free).
- `graph_score` — Jaccard overlap between the drug's pathway neighborhood
  (`drug → TARGETS → protein → PARTICIPATES_IN → pathway`) and the disease's
  neighborhood (`disease → CAUSES → gene → ENCODES → protein → PARTICIPATES_IN →
  pathway`). `[0, 1]`, higher is better.
- `fused_score` — RRF of the two rankings, `k=60`:
  `1/(60+model_rank) + 1/(60+graph_rank)`. Response is sorted by this.
- `model_rank`, `graph_rank` — 1-indexed **within the returned candidate set**.
  When `include_already_approved=False`, approved drugs are excluded *before*
  ranking (fix C4).

**Diagnosis (`/diagnose`)**

- `jaccard_score` — `|input ∩ disease.symptoms| / |input ∪ disease.symptoms|`.
- `idf_score` — sum of smoothed IDF weights of matched symptoms.
  `idf(s) = log((1+N)/(1+df(s)))+1`; rare symptoms count more.
- `fused_score` — RRF of both rankings, `k=60`.
- `unresolved_inputs` — input tokens that could not be resolved. Surfaced
  explicitly so the UI can flag them (fix C3).

---

## Testing

```
pytest tests/regression tests/integration   # 88 tests
python run.py smoke                          # 17 smoke checks
```

| Suite | Location | Count | What it covers |
|---|---|---|---|
| Regression | `tests/regression/test_backend.py` | 23 | One pin per named defect (C1-C5, H1-H7, M1-M4) |
| Integration | `tests/integration/` | 65 | Full HTTP surface, schema, error cases, dual-mount |
| E2E smoke | `tests/e2e/smoke.py` | 17 | Real-data ranking pins (Tay-Sachs, Fabry, NPC) |

**Backend-parity testing (Step 6):** the integration tests are backend-agnostic.
Run `KG_BACKEND=neo4j pytest tests/integration` after Phase 1 ingest to verify
the Neo4j backend produces identical API responses.

---

## Phase progress

| Phase | Status | Key deliverable |
|---|---|---|
| Pre-Phase-1 refactor | ✅ **done** | `app/` layout, `create_app()`, `lifespan`, DI aliases, Ruff, 88-test suite |
| Docker scaffolding | ✅ **done** | `compose.yml`, `Dockerfile.backend`, `init.cypher` |
| Phase 1 — ingestor code | ✅ **done** | PrimeKG · DrugCentral · HPO · Orphanet · Reactome · `fetch_all.py` |
| Phase 1 — KG backend | ✅ **done** | `KGBackend` Protocol · `Neo4jBackend` · `lifespan` wired |
| Phase 1 — data ingest | 🔲 pending user | `docker compose up -d neo4j` → `python -m app.etl.fetch_all` → `python -m app.etl.ingest.all` |
| Phase 1 — Neo4j live | 🔲 pending data | `KG_BACKEND=neo4j` + re-run 88+17 suite |
| Phase 2 — PyKEEN + CompGCN | 🔲 future | After Phase 1 verification |
| Phase 3 — Cypher evidence paths | 🔲 future | Replace in-memory DFS in `Neo4jBackend` |
| Phase 4 — FAISS + Resnik diagnosis | 🔲 future | Second scorer in `DiagnoseService` |
| Phase 5 — NER enrichment | 🔲 optional | `app/ner/` domain |
| Phase 6 — React frontend | 🔲 future | Replace `frontend/index.html` |

---

## Configuration

All settings are in `app/core/config.py` as a `pydantic-settings` `Settings`
class that reads from `.env`.  Copy `.env.example` to `.env` and edit before
running the Phase 1 stack.

Key variables:

| Variable | Default | Notes |
|---|---|---|
| `KG_BACKEND` | `networkx` | `neo4j` after Phase 1 ingest |
| `NEO4J_URI` | `bolt://localhost:7687` | Bolt URL |
| `NEO4J_PASSWORD` | `changethis_dev_only` | **Must change** before production |
| `DATAVERSE_API_TOKEN` | _(empty)_ | Required for PrimeKG download from Harvard Dataverse |
| `DISEASE_SCOPE` | `lsd` | `lsd` · `lsd_extended` · `all` |
| `LOG_LEVEL` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |

---

## Development

```bash
# Install with dev extras
pip install -e ".[dev]"

# Lint + format (Ruff)
bash scripts/lint.sh
# or:
ruff check app tests --fix && ruff format app tests

# Dev convenience (serves + watches)
bash scripts/dev.sh serve
```

Pre-commit hook (optional):

```bash
pre-commit install
```

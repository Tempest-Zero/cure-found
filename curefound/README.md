# CureFound

**Drug repurposing on a curated biomedical knowledge graph for rare lysosomal
storage disorders.** RotatE knowledge-graph embeddings (PyTorch training,
NumPy inference) + Jaccard pathway-overlap + Reciprocal Rank Fusion, served
behind a FastAPI backend with a React/Vite frontend. KG: 673 entities, 1057
edges across 7 relation types — covering 13 LSDs + Cystic Fibrosis +
Huntington, enriched with 894 HPO phenotype annotations from the official
[`phenotype.hpoa`](https://github.com/obophenotype/human-phenotype-ontology)
release.

> ⚠ **Research prototype. Not for clinical use.**

---

## What it does

Two demo flows, both working end-to-end against the 99-node seed KG:

1. **Drug repurposing.** Given a rare disease (e.g. Niemann-Pick C), rank drug
   candidates most likely to treat it. Hybrid ranker: **RotatE** link-prediction
   `(drug, TREATS, disease)` + Jaccard pathway-neighborhood overlap + Reciprocal
   Rank Fusion. Returns evidence paths per candidate for explainability.

2. **Symptom-based diagnosis.** Given HPO phenotype terms (e.g. cherry-red spot +
   hypotonia + seizures), rank candidate diseases. Hybrid ranker: Jaccard symptom
   overlap + IDF-weighted match + RRF. Unresolvable input tokens are reported
   explicitly rather than silently dropped.

Plus a free-form **KG explorer**: search any node, view its k-hop subgraph as an
interactive Cytoscape.js graph.

---

## Quickstart (local dev)

```bash
cd curefound
python -m venv .venv && source .venv/Scripts/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Train RotatE on the seed KG (~20 min on CPU; artefacts -> data/artifacts/)
python -m app.ml.rotate

# Serve API + frontend
python -m uvicorn app.main:app --reload
#   API:           http://localhost:8000/
#   OpenAPI docs:  http://localhost:8000/docs
#   Stats:         http://localhost:8000/stats

# Frontend dev server (separate terminal, talks to FastAPI on :8000)
cd frontend && npm install && npm run dev
#   http://localhost:5173/
```

Tests:

```bash
pytest tests/regression tests/unit -q       # 23 + 6 = 29 tests, ~30 s
```

Held-out evaluation with bootstrap CIs:

```bash
python -m app.ml.eval --epochs 300 --bootstrap 2000
# Writes data/artifacts/eval_report.json with per-fold ranks and CI bounds.
```

---

## Architecture

```
curefound/
├── app/                            Python package
│   ├── main.py                     create_app() factory + module-level app
│   ├── core/
│   │   ├── config.py               Settings(BaseSettings) -- reads .env
│   │   ├── logging.py              structlog + asgi-correlation-id
│   │   ├── exceptions.py           AppError hierarchy + FastAPI handlers
│   │   ├── lifespan.py             startup: load KG + RotatE
│   │   └── paths.py                project-root resolution
│   ├── kg/
│   │   ├── loader.py               NetworkX KG (single in-process backend)
│   │   ├── router.py               /stats /search /node /subgraph
│   │   ├── schemas.py              NodeBrief, NodeDetail, SubgraphResponse
│   │   └── deps.py                 KGDep = Annotated[KG, Depends(get_kg)]
│   ├── repurpose/
│   │   ├── service.py              RotatE + Jaccard + RRF pipeline
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
│   │   ├── rotate.py               RotatE trainer (PyTorch) + numpy inference
│   │   ├── deps.py                 KGEArtifacts dependency injection
│   │   └── eval.py                 LOO filtered evaluation + bootstrap CIs
│   └── etl/
│       └── expand_hpo_lsd.py       Filter HPO HPOA to LSD scope, merge into KG
├── tests/
│   ├── conftest.py                 Shared fixtures: test_app, sync/async client
│   ├── regression/test_backend.py  23 pins -- one per named defect
│   ├── unit/                       Pure-logic tests for kg/loader, services
│   └── e2e/smoke.py                End-to-end demo flow checks
├── frontend/
│   ├── index.html                  Vite entry
│   ├── vite.config.ts              base: "/ui/" + manualChunks code-split
│   ├── package.json                React 18 + Tailwind v4 + Framer Motion + GSAP
│   └── src/
│       ├── App.tsx                 NavBar + Hero + lazy-loaded sections
│       ├── components/             Repurpose, Diagnose, Explorer, Eval, Methods
│       └── lib/                    types + api() + ApiStatusChip
├── data/
│   ├── seed/kg.json                673 nodes / 1057 edges (HPO-expanded LSD KG)
│   ├── seed/kg-mvp.json            Original 99-node curated baseline
│   └── artifacts/                  RotatE weights + metadata + eval report
├── docker/Dockerfile               Multi-stage: Vite -> Python slim (single image)
├── fly.toml                        Fly.io deploy config (remote builder)
├── .github/workflows/ci.yml        Lint + tests + Docker build on push
├── .env.example                    All Settings fields documented
├── pyproject.toml                  Runtime + dev deps, ruff + pytest config
└── run.py                          Cross-platform task runner
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

## Seed KG (current state, post HPO-HPOA expansion)

```
673 entities · 7 relations · 1057 triples
  Disease: 13     Gene: 13       Protein: 16
  Drug:    19     Pathway: 12    Symptom: 600 (26 curated + 574 from HPO HPOA)

  HAS_PHENOTYPE:   962      (+894 from real HPO HPOA disease-phenotype rows)
  PARTICIPATES_IN:  31      ENCODES:  13      CAUSES:  14
  TARGETS:          19      TREATS:   16      ASSOCIATED_WITH:  2
```

Focus: **Lysosomal Storage Disorders** (Gaucher, Fabry, Niemann-Pick A/B/C, Pompe,
Tay-Sachs, Krabbe, MPS-I/II, MLD) + Cystic Fibrosis and Huntington as non-LSD
controls.

**Provenance.** The original 99-node hand-curated seed remains in
`data/seed/kg-mvp.json`. The expanded version was produced by
`python -m app.etl.expand_hpo_lsd`, which filters the official
`phenotype.hpoa` annotations to OMIM/ORPHA IDs that match our 13 diseases
(894 added rows after deduplication, qualifier!=NOT, aspect=P). New
phenotype nodes carry the `S:HP_NNNNNNN` id format. Disease and drug
vocabularies are intentionally **frozen** so the TREATS evaluation set
stays the same 16 triples and the comparison with the pre-expansion
RotatE numbers is meaningful.

---

## The model — RotatE

**RotatE** (Sun et al., *ICLR 2019*) — *Knowledge Graph Embedding by Relational
Rotation in Complex Space*. Implemented in **PyTorch** end-to-end with `nn.Embedding`
layers, Adam optimizer, and self-adversarial sigmoid loss.

**Geometry.** Each entity is a complex vector `h ∈ ℂ^d`; each relation is a unit-modulus
complex vector `r ∈ ℂ^d` parameterized as `r = e^(iθ)` (only the phase angles θ ∈ ℝ^d
are learned). The score function is

```
f(h, r, t) = −‖h ∘ r − t‖₂        (∘ = element-wise complex multiplication)
```

i.e. `t` should be reachable from `h` by per-coordinate rotation by the relation's
phase. This is strictly more expressive than TransE's translation `h + r ≈ t` and
structurally encodes three relation patterns present in our KG:

| Pattern | Example | Why TransE fails | Why RotatE works |
|---|---|---|---|
| Antisymmetric | `Drug TREATS Disease` (not the reverse) | `h + r = t` does not enforce `t + r ≠ h` | `h ∘ r = t` and `t ∘ r ≠ h` whenever `θ ≠ 0, π` |
| Symmetric | `Gene ASSOCIATED_WITH Gene` | forces `r = 0`, collapsing the embedding | `θ = 0` is the identity rotation — no collapse |
| Compositional | `Gene→ENCODES→Protein→PARTICIPATES_IN→Pathway` | translations don't compose meaningfully | rotations compose by phase addition: `θ₁ + θ₂` |

**Training (`app/ml/rotate.py`).** PyTorch `nn.Module` with `nn.Embedding(n_entities,
2·dim)` for real‖imaginary entity parts and `nn.Embedding(n_relations, dim)` for
relation phases. Loss is the self-adversarial negative-sampling form from the paper:

```
L = −log σ(γ − d_pos) − Σⱼ p(h'ⱼ, r, t'ⱼ) · log σ(d_neg,ⱼ − γ)
p(h'ⱼ, r, t'ⱼ) = softmax(α · score(h'ⱼ, r, t'ⱼ))      (self-adversarial weighting)
```

with γ = 6.0, α = 0.5, Adam lr = 1e-3, 64 negatives per positive, gradient clip = 1.0.

**Inference.** Pure NumPy from saved `data/artifacts/rotate.npz`. PyTorch is only
needed at training time; the API server loads complex64 numpy arrays and computes
`−‖h ∘ r − t‖` directly. Cold-start cost: ~3 ms.

### Held-out evaluation

`python -m app.ml.eval` runs the Sun-2019 / PyKEEN leave-one-out filtered
protocol: retrain RotatE on N-1 `TREATS` triples, rank every Drug as a
possible head for each held-out tail, filter other known-true heads
before ranking. Report written to `data/artifacts/eval_report.json`,
including a non-parametric **bootstrap-95% CI** over the per-fold ranks.

> Numbers below are placeholders pending the post-HPO-expansion eval run
> (in flight on CPU; this README will be regenerated once
> `eval_report.json` lands). The methodology table — what each model
> family structurally supports — stays valid regardless of the headline
> numbers.

**KG: 673 entities · 1057 edges · 16 held-out TREATS triples · 19 Drug candidates.**

| Metric | TransE (legacy 99-node) | RotatE (post-HPO 673-node) | Bootstrap CI |
|---|---|---|---|
| MRR (filtered) | 0.131 | _pending_ | _pending_ |
| Hits@1 | 0.000 | _pending_ | _pending_ |
| Hits@3 | 0.062 | _pending_ | _pending_ |
| Hits@10 | 0.562 | _pending_ | _pending_ |
| Mean rank | 9.88 | _pending_ | _pending_ |

**Why this counts as deep learning.** RotatE is an end-to-end neural
representation-learning model — trainable embedding layers, Adam,
self-adversarial sigmoid loss, gradient backprop. The depth of
knowledge-graph embedding methods lies in the learned feature space,
not stacked layers (Hamilton, Ying & Leskovec, NeurIPS 2017). The
in-progress GNN comparison adds R-GCN and CompGCN (PyKEEN) for an
explicit message-passing baseline.

### Diagnostic sanity-check on hand-picked LSD profiles

| Input symptoms | Top-1 predicted | Correct? |
|---|---|---|
| splenomegaly + anemia + bone pain + hepatomegaly + thrombocytopenia | **Gaucher** | ✅ |
| angiokeratoma + renal + neuropathy + cardiomyopathy | **Fabry** | ✅ |
| hepatomegaly + splenomegaly + VSGP + ataxia + seizures + devdelay | **Niemann-Pick C** | ✅ |
| cherry-red spot + hypotonia + devdelay + seizures | **Tay-Sachs** | ✅ |

Pinned as smoke-style assertions in `tests/regression/test_backend.py`.

---

## Scoring semantics

All scores exposed by the API carry `description=` in the OpenAPI schema.  Summary:

**Repurposing (`/repurpose`)**

- `model_score` — RotatE: `−‖h ∘ r − t‖₂` in complex space, where `r = e^(iθ)`.
  Higher is better. Not comparable across retrains (the embedding space has
  global phase symmetry).
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

```bash
pytest tests/regression tests/unit -q       # ~30 s
python run.py smoke                          # end-to-end demo flow checks
```

| Suite | Location | What it covers |
|---|---|---|
| Regression | `tests/regression/test_backend.py` | One pin per named defect that's been fixed in production |
| Unit | `tests/unit/` | Pure-logic tests: KG loader, repurpose service ranking math, RotatE inference shape |
| E2E smoke | `tests/e2e/smoke.py` | Real-data ranking pins (Tay-Sachs, Fabry, NPC top-1 hits) |

---

## Roadmap

| Milestone | Status |
|---|---|
| Curated 99-node LSD seed KG | ✅ shipped |
| RotatE in PyTorch + NumPy inference | ✅ shipped |
| Leave-one-out filtered eval + bootstrap-95% CIs | ✅ shipped |
| FastAPI + Pydantic v2 backend | ✅ shipped |
| React/Vite frontend with code-split bundles | ✅ shipped |
| HPO HPOA expansion (894 HAS_PHENOTYPE edges) | ✅ shipped |
| GNN comparison study (R-GCN + CompGCN via PyKEEN) | 🟡 in progress |
| Multi-stage Docker image + Fly.io deploy | 🟡 in progress |
| GitHub Actions CI (lint + test + image build) | ✅ wired |
| Time-split eval on `approval_year` (PyKEEN pipeline) | 🔲 future |

---

## Configuration

All settings live in `app/core/config.py` as a `pydantic-settings` `Settings`
class that reads from `.env`. Copy `.env.example` to `.env` and edit.

Key variables:

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `local` | `local` enables `/docs`; anything else hides it |
| `KG_BACKEND` | `networkx` | Single in-process backend |
| `SEED_KG_PATH` | `data/seed/kg.json` | Switch to `kg-mvp.json` for the original 99-node baseline |
| `DISEASE_SCOPE` | `lsd` | `lsd` · `lsd_extended` · `all` |
| `LOG_LEVEL` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |

---

## Development

```bash
pip install -e ".[dev]"
ruff check app tests --fix && ruff format app tests
pytest tests/regression tests/unit -q
```

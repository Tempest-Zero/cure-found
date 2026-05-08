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

Two demo flows, both working end-to-end against the 673-node LSD-scoped KG:

1. **Drug repurposing.** Given a rare disease (e.g. Niemann-Pick C), rank drug
   candidates most likely to treat it. Hybrid ranker: a **knowledge-graph
   embedding** model scores `(drug, TREATS, disease)` link-plausibility, fused
   with Jaccard pathway-neighborhood overlap via Reciprocal Rank Fusion (k=60).
   Three KG-embedding backends are wired in: **RotatE** (always shipped),
   **R-GCN** and **CompGCN** (loaded if their PyKEEN-trained artifacts are
   bundled). The chosen model is per-request via the `model` field; the API
   returns `503 model_unavailable` if the requested artifacts aren't on disk.
   Returns evidence paths per candidate for explainability.

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
| GET  | `/repurpose/models` | List the KGE backends loaded in this deploy |
| POST | `/repurpose` | Ranked drug candidates with evidence paths |
| POST | `/diagnose`  | Ranked disease candidates from HPO symptom ids |

Live OpenAPI: `GET /docs` (local environment only).

### Quick examples

```bash
# Which scoring backends are loaded in this deploy?
curl http://localhost:8000/repurpose/models
# {"models": ["rotate"]}              # baseline deploy (no GNN artifacts shipped)
# {"models": ["compgcn", "rgcn", "rotate"]}   # full deploy

# Repurposing for Niemann-Pick C (canonical or MONDO id both work).
# `model` is optional and defaults to "rotate".
curl -X POST http://localhost:8000/repurpose \
  -H "Content-Type: application/json" \
  -d '{"disease_id": "D:NPC", "top_k": 5, "include_already_approved": false, "model": "rotate"}'

curl -X POST http://localhost:8000/repurpose \
  -H "Content-Type: application/json" \
  -d '{"disease_id": "MONDO:0009937", "top_k": 5, "model": "compgcn"}'

# If the requested model wasn't bundled, the API returns 503 with
# {"detail": {"error": "model_unavailable", "available_models": [...]}}.

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
including a non-parametric **bootstrap-95% CI** over the per-fold ranks
(`--bootstrap 2000`).

**KG: 673 entities · 1,057 edges · 16 held-out TREATS triples · 17–19 Drug candidates per fold.**

| Metric | RotatE (mean) | Bootstrap 95% CI | R-GCN | CompGCN |
|---|---|---|---|---|
| MRR (filtered) | 0.146 | [0.085, 0.218] | _pending T4 retrain_ | _pending T4 retrain_ |
| Hits@1 | 0.000 | [0.000, 0.000] | _pending_ | _pending_ |
| Hits@3 | 0.125 | [0.000, 0.313] | _pending_ | _pending_ |
| Hits@10 | 0.375 | [0.125, 0.625] | _pending_ | _pending_ |
| Mean rank ↓ | 10.94 | [8.63, 13.31] | _pending_ | _pending_ |

R-GCN and CompGCN train via `scripts/colab_gnn_training.ipynb` on a free Colab T4
(~30–60 min); the resulting `rgcn.npz` + `compgcn.npz` artifacts drop into
`data/artifacts/` and the lifespan picks them up automatically next boot. The
runtime never imports PyTorch — DistMult-scored embeddings are evaluated as
pure-NumPy tensor contractions (`app/ml/distmult.py`).

**Honest failures (RotatE, post-HPO).** Three reviewer-flagged cases:

| Drug → Disease | Rank | Why |
|---|---|---|
| Arimoclomol → Niemann-Pick C | 12 / 17 | HSP-co-inducer mechanism is unrepresented in the KG. |
| N-acetyl-L-leucine → Niemann-Pick C | 8 / 17 | Mid-pack — moved up from 14 thanks to HPO overlap with Miglustat (rank 2). |
| Tetrabenazine → Huntington | 4 / 19 | Top-5 — symptomatic VMAT2 link captured. |

Per-fold ranks live in `data/artifacts/eval_report.json::per_item`; bright spots
include Eliglustat → Gaucher rank 2 and Miglustat → NPC rank 2.

**Why this counts as deep learning.** Each KGE model is an end-to-end
representation-learning system — trainable embedding tables, Adam, sigmoid /
contrastive loss, gradient backprop. R-GCN and CompGCN add explicit
**message-passing** layers on top of the embedding tables (Schlichtkrull 2018;
Vashishth 2020). Comparing all three on the same LOO protocol is the headline
ML experiment of the project.

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

- `model_score` — depends on the chosen `model`:
  - **RotatE**: `−‖h ∘ r − t‖₂` in complex space, where `r = e^(iθ)`.
  - **R-GCN / CompGCN**: DistMult head `Σ_d h_d · r_d · t_d` over message-passed
    embeddings (the GNN message-passing happens at training time inside PyKEEN;
    the runtime container loads the resulting embedding tables and scores them
    in NumPy).

  Higher is better. Scale is per-model and per-retrain — never compare scores
  across them (compare ranks instead).
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
| Per-request model selector (`/repurpose/models`) | ✅ shipped |
| R-GCN + CompGCN trainer (PyKEEN) + Colab notebook | ✅ shipped |
| GNN artifacts trained on T4 + LOO numbers | 🟡 in progress |
| Multi-stage Docker image + Fly.io deploy | 🟡 in progress |
| GitHub Actions CI (lint + test + image build) | ✅ wired |
| Time-split eval on `approval_year` (PyKEEN pipeline) | 🔲 future |

---

## Training the GNN baselines (R-GCN + CompGCN, on Colab T4)

PyTorch + PyKEEN are heavy; the production container deliberately omits both
(image stays ~250 MB instead of ~750 MB). To train the GNN baselines, use the
included Colab notebook — it clones the repo, installs PyKEEN, runs the LOO
eval with bootstrap CIs, and packages the artifacts for download:

1. Open `scripts/colab_gnn_training.ipynb` in Google Colab.
2. Runtime → Change runtime type → **T4 GPU**.
3. Run all cells (~30–60 min for both R-GCN and CompGCN combined).
4. The last cell downloads `gnn_artifacts.zip`. Unzip into `data/artifacts/`:
   ```
   data/artifacts/rgcn.npz  rgcn_meta.json
   data/artifacts/compgcn.npz  compgcn_meta.json
   ```
5. Restart the API (`python -m uvicorn app.main:app --reload`); on boot the
   lifespan loads the new artifacts and `GET /repurpose/models` will report
   `["compgcn", "rgcn", "rotate"]`.

To train locally instead (CPU, very slow — `[ml]` adds PyKEEN; `torch` is already a runtime dep):

```bash
pip install -e ".[dev,ml]"
python scripts/train_gnns_pykeen.py --models rgcn,compgcn --epochs 300 --bootstrap 2000
```

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

---

## Deploying to Fly.io (zero local Docker required)

The `docker/Dockerfile` is multi-stage and Fly's **remote builder** runs the
build for you, so you don't need Docker Desktop on your machine.

```bash
# One-time:
curl -L https://fly.io/install.sh | sh        # or `iwr https://fly.io/install.ps1 -useb | iex` on PowerShell
fly auth login                                # browser auth

# First deploy: rewrites fly.toml with a unique app slug, then deploys.
# --remote-only forces the build to happen on Fly's builder (no local docker daemon).
fly launch --copy-config --no-deploy
fly deploy --remote-only

# Open the live URL.
fly open
fly logs                                      # stream container logs
```

What the production image ships:

- `app/` (FastAPI backend), `app/ml/rotate.py` + `app/ml/distmult.py`
  (pure-NumPy inference)
- `data/seed/kg.json` (673-node HPO-expanded KG)
- `data/artifacts/rotate.{npz,_meta.json}` (always)
- `data/artifacts/{rgcn,compgcn}.{npz,_meta.json}` (only if you copied them in
  before deploying — produced by the Colab notebook)
- `frontend/dist/` (Vite-built React SPA, mounted at `/ui/`)

What it does **not** ship: PyTorch, PyKEEN, raw data, training scripts. Image
size stays around 250 MB.

After deploy, verify:

```bash
curl https://<your-app>.fly.dev/health           # 200 + KG version
curl https://<your-app>.fly.dev/repurpose/models # {"models": [...]} 
curl -X POST https://<your-app>.fly.dev/repurpose \
  -H "Content-Type: application/json" \
  -d '{"disease_id":"D:NPC","top_k":5}'
# Visit https://<your-app>.fly.dev/ in a browser for the React UI.
```

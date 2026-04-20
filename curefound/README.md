# CureFound — MVP prototype

**Status:** working end-to-end prototype, post-hardening. 99-node seed KG, TransE embeddings, FastAPI + Cytoscape.js UI. This is the **MVP** described in the FYP plan (`C:\Users\OGDCL\.claude\plans\vjndncc-shiny-puppy.md`). The seams match the final architecture — see [Swap map](#swap-map-where-the-mvp-differs-from-the-final-design) for what to replace in each phase.

> ⚠ **Research prototype. Not for clinical use.**

A pre-Phase-1 backend-correctness sprint landed 12 defect fixes (C1-C5, H1-H7, M1-M4): proper leave-one-out evaluation replacing the old training-data leakage numbers, deterministic BFS subgraph, a Cytoscape `source`-field collision that previously dropped every edge from the graph view, stricter Pydantic validation, candidate-set-first ranking, O(1) xref resolution, schema validation, artifact-staleness detection, and an explicit `unresolved_inputs` channel so no input fails silently. See `tests/test_backend.py` for one regression guard per defect.

---

## What it does

Two demo flows, both working:

1. **Drug repurposing.** Given a disease (e.g. Niemann-Pick disease type C), rank drugs most likely to treat it. Uses a hybrid ranker: (a) TransE link-prediction score for `(drug, TREATS, disease)`, (b) Jaccard overlap between the drug's pathway neighborhood and the disease's pathway neighborhood, (c) Reciprocal Rank Fusion. Also returns up to 3 short evidence paths per candidate.
2. **Symptom-based diagnosis.** Given a set of HPO phenotype terms (e.g. `HP:0010729` cherry-red spot + `HP:0001252` hypotonia + ...), rank candidate diseases. Hybrid ranker: Jaccard + IDF-weighted symptom match + RRF.

Plus a free-form **KG explorer** (search any node, see its k-hop neighborhood as an interactive graph).

---

## Quickstart (60 seconds)

```bash
cd curefound

# 1. Build the seed KG (regenerates data/seed/kg.json)
python run.py seed

# 2. Train TransE (~6 seconds; saves to data/artifacts/)
python run.py train

# 3. Start the API + UI (default port 8000)
python run.py serve

# Open http://localhost:8000/   →   interactive UI
# Open http://localhost:8000/docs →  OpenAPI / Swagger
```

End-to-end test without a server (uses FastAPI TestClient):

```bash
python run.py smoke
```

Dependencies: Python 3.11+, `fastapi`, `uvicorn`, `pydantic`, `numpy`, `networkx`. Install via `pip install fastapi uvicorn pydantic numpy networkx`. No PyTorch / PyKEEN / Neo4j required for the MVP.

---

## Repo layout

```
curefound/
├── data/
│   ├── seed/kg.json                # generated; 99 nodes, 163 edges
│   └── artifacts/                  # TransE embeddings + metadata (generated)
├── etl/
│   ├── build_seed_kg.py            # hand-curated LSD-focused KG generator
│   └── id_map_service.py           # canonical-ID service (xref → canonical_id)
├── kg/
│   └── loader.py                   # NetworkX KG + search / subgraph / evidence paths
├── ml/
│   └── transe.py                   # TransE trainer, pure NumPy
├── api/
│   ├── main.py                     # FastAPI app (all endpoints)
│   └── services/
│       ├── repurpose.py            # drug-repurposing inference
│       └── diagnose.py             # symptom-matching inference
├── frontend/
│   ├── index.html                  # single-page Cytoscape.js UI (3 tabs)
│   ├── style.css
│   └── app.js
├── tests/
│   └── smoke.py                    # 17 end-to-end checks
├── Makefile                        # GNU make tasks (optional)
├── run.py                          # cross-platform task runner
└── README.md                       # this file
```

---

## API reference

All endpoints live under `http://localhost:8000/`.

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health` | liveness + KG version |
| GET  | `/stats`  | node / relation / edge counts |
| GET  | `/search?q=&type=&limit=` | autocomplete search |
| GET  | `/node/{node_id}` | node detail + xrefs + degree |
| GET  | `/subgraph?node_id=&k=&max_nodes=` | Cytoscape-ready subgraph |
| POST | `/repurpose` | ranked drug candidates with evidence paths |
| POST | `/diagnose`  | ranked disease candidates from HPO ids |

Live OpenAPI: `GET /docs`.

### Example

```bash
# Repurposing for Niemann-Pick C
curl -X POST http://localhost:8000/repurpose \
  -H "Content-Type: application/json" \
  -d '{"disease_id": "D:NPC", "top_k": 5, "include_already_approved": false}'

# MONDO id also works
curl -X POST http://localhost:8000/repurpose \
  -H "Content-Type: application/json" \
  -d '{"disease_id": "MONDO:0009937", "top_k": 5}'

# Diagnose from HPO ids
curl -X POST http://localhost:8000/diagnose \
  -H "Content-Type: application/json" \
  -d '{"symptoms": ["HP:0010729","HP:0001252","HP:0001263","HP:0001250"], "top_k": 5}'
```

---

## Seed KG stats

```
99 entities · 7 relations · 163 triples
  Disease: 13   Gene: 13   Protein: 16
  Drug:    19   Pathway: 12   Symptom: 26

  CAUSES: 14    ENCODES: 13   TARGETS: 19
  TREATS: 16    HAS_PHENOTYPE: 68
  PARTICIPATES_IN: 31         ASSOCIATED_WITH: 2
```

Focus cluster: **Lysosomal Storage Disorders** (Gaucher, Fabry, Niemann-Pick A/B/C, Pompe, Tay-Sachs, Krabbe, MPS-I, MPS-II, MLD) plus CF and HD as non-LSD controls.

---

## Held-out evaluation (leave-one-out, filtered)

`python ml/eval.py` runs the Bordes-2013 / PyKEEN-style protocol on every `TREATS` triple: retrain TransE on the remaining N−1 triples, score every Drug as a head for `(TREATS, t)`, and filter out other known-true heads for the same tail before ranking. The report is written to `data/artifacts/eval_report.json`.

**Seed KG, 16 held-out `TREATS` triples, 19 Drug candidates, TransE dim=64, 800 epochs, seed=42:**

| Metric | Value |
|---|---|
| Mean rank (filtered) | **9.88 / 19** |
| MRR (filtered) | **0.131** |
| Hits@1 | **0.000** |
| Hits@3 | **0.062** |
| Hits@10 | **0.562** |

These numbers are weak — as expected for pure-NumPy TransE on a 99-node graph with 16 training signals. They exist to (a) give the thesis an **honest baseline** that the Phase-2 PyKEEN + CompGCN pipeline can beat, (b) provide a repeatable protocol that survives the Phase-2 swap unchanged, and (c) make the hybrid ranker's value visible: the graph-score (Jaccard pathway overlap) carries most of the real signal on this graph size, which is why `/repurpose` still surfaces correct LSD candidates under RRF fusion.

**Known repurposing candidates that the hybrid ranker (TransE + Jaccard + RRF) still surfaces in the top-10** (not in the `TREATS` graph — held out by design):

- **Hydroxypropyl-β-cyclodextrin** for Niemann-Pick C (real-world candidate, clinical-trial stage)
- **Ambroxol** for Gaucher (real-world chaperone candidate)
- **Vorinostat** / **Rapamycin** appear mid-table for LSDs via autophagy / HDAC pathways

### Diagnostic accuracy on hand-picked LSD profiles

| Input symptoms | Top-1 predicted | Correct? |
|---|---|---|
| splenomegaly + anemia + bone pain + hepatomegaly + thrombocytopenia | **Gaucher** | ✅ |
| angiokeratoma + renal + neuropathy + cardiomyopathy | **Fabry** | ✅ |
| hepatomegaly + splenomegaly + VSGP + ataxia + seizures + devdelay | **Niemann-Pick C** | ✅ |
| cherry-red spot + hypotonia + devdelay + seizures | **Tay-Sachs** | ✅ |

Each of these profiles is pinned by a smoke check in `tests/smoke.py` and `tests/test_backend.py`.

### Training-set sanity (NOT a metric)

For comparison only — **these numbers were in the README before the hardening sprint and misrepresented training-set memorization as generalization**. They are kept here, relabeled, so the thesis can show the before/after and so future reviewers cannot mistake them for held-out results. Rank of the true disease tail when its own `TREATS` triple is in the training set:

| Drug | True disease | Rank (training-set) |
|---|---|---|
| Imiglucerase | Gaucher | 1/13 |
| Agalsidase beta | Fabry | 1/13 |
| Miglustat | Niemann-Pick C | 1/13 |
| Alglucosidase alfa | Pompe | 2/13 |
| Laronidase | MPS-I | 5/13 |

---

## Scoring semantics

Every score exposed by the API is documented here so reviewers can trace a ranking back to its constituents. Same field names are used by `/repurpose` and `/diagnose` responses and carry `description=…` in the OpenAPI schema.

**Repurposing (`/repurpose`)**

- `model_score` — TransE score for `(drug, TREATS, disease)`, computed as `-||h + r − t||₂` (negative L2 distance between the translated head+relation and the tail). Higher is better; typical range on this KG is roughly `[−10, −2]`. Absolute values are not comparable across retrains because the embedding space is rotation-free.
- `graph_score` — Jaccard overlap between the drug's pathway neighborhood (`drug → TARGETS → protein → PARTICIPATES_IN → pathway`) and the disease's pathway neighborhood (`disease → CAUSES → gene → ENCODES → protein → PARTICIPATES_IN → pathway`). In `[0, 1]`; higher is better.
- `fused_score` — Reciprocal Rank Fusion of the two rankings with `k = 60`: `1/(60 + model_rank) + 1/(60 + graph_rank)`. Higher is better. This is what the response is sorted by.
- `model_rank`, `graph_rank` — **1-indexed within the returned candidate universe.** When `include_already_approved=False`, approved drugs are excluded *before* ranking, so ranks run from 1 to `len(candidates)` — not across all 19 drugs in the KG. This was fix C4.

**Diagnosis (`/diagnose`)**

- `jaccard_score` — `|input ∩ disease.symptoms| / |input ∪ disease.symptoms|`. In `[0, 1]`.
- `idf_score` — sum of smoothed IDF weights of matched symptoms. Smoothed-IDF follows sklearn's `TfidfVectorizer`: `idf(s) = log((1 + N_diseases) / (1 + df(s))) + 1`. A symptom present in every disease gets `idf = 1` (not 0), a symptom unique to one disease gets the maximum weight. Higher is better.
- `fused_score` — RRF of the two rankings with `k = 60`. Higher is better; response is sorted by this.
- `matched_symptoms` / `missing_symptoms` — disease symptoms respectively present in / absent from the input set; both sorted deterministically by canonical id.
- `unresolved_inputs` — HPO ids the input resolver could not map. Surfaced as a first-class field so the UI can flag them instead of silently dropping (fix C3).

---

## Swap map (where the MVP differs from the final design)

Each MVP module is a placeholder with a clean interface. In each phase of the FYP plan, the body gets replaced; callers don't change.

| MVP module | Final-design replacement | Phase |
|---|---|---|
| `etl/build_seed_kg.py` (hand-curated ~100 nodes) | `etl/ingest_primekg.py`, `etl/ingest_drugcentral.py`, `etl/ingest_hpo.py`, `etl/ingest_orphanet.py`, `etl/ingest_reactome.py` → PrimeKG-hybrid KG | Phase 1 |
| `etl/id_map_service.py` (xref dict from seed) | MONDO SSSOM + HGNC + UniProt + OXO + Bioregistry, fail-loud unmapped | Phase 1 |
| `kg/loader.py` (NetworkX in-memory) | Neo4j 5.x + Cypher queries; same accessor contract | Phase 1 |
| `ml/transe.py` (pure-NumPy TransE) | PyKEEN pipeline (TransE + RotatE + ComplEx + DistMult + **CompGCN**); time-split; filtered MRR; bootstrap CI | Phase 2 |
| Jaccard pathway score in `repurpose.py` | keep as baseline + GNN score from CompGCN | Phase 2 |
| Jaccard + IDF in `diagnose.py` | add FAISS over HPO vectors + Resnik similarity over HPO DAG | Phase 4 |
| — (no NER in MVP) | `ner/pubmedbert_ner.py`, `ner/setfit_rare_disease.py`; enriches KG with `MENTIONED_WITH` weak edges | Phase 5 |
| single-page `frontend/index.html` | React 18 + Vite + TypeScript; same Cytoscape.js component | Phase 6 |
| no Docker | `docker-compose.yml` with Neo4j + FastAPI + frontend | Phase 6 |

**What already matches the final design:**
- Entity / relation vocabulary and edge directions.
- Canonical ID xref scheme (MONDO / HGNC / UniProt / DrugCentral / Reactome / HPO).
- Two inference endpoints with the same request / response schemas.
- RRF fusion of embedding + graph scores.
- Evidence-path return structure for explainability.
- Server-side subgraph cap (plan Risk #8 — Cytoscape rendering cap).

---

## Intentional MVP cuts (documented)

- **No PrimeKG / Neo4j download** — requires 600 MB and a Neo4j server, not worth it until Phase 1.
- **No time-split on `TREATS`** — the seed KG has `approval_year` on every `TREATS` edge, so the split can be enabled by passing `cutoff_year` into `ml/transe.py` when the graph is big enough (currently only 16 `TREATS` edges, too few for meaningful split).
- **No GNN baseline** — Phase 2 work; CompGCN requires PyG + CUDA.
- **No Hetionet baseline reproduction** — Phase 2 work; requires a larger dataset + PyKEEN.
- **No NER enrichment** — Phase 5 work; requires PubMedBERT + ~30-80k PubMed abstracts.
- **No Docker** — Phase 6 work.
- **Evidence path finder has some duplicate-path artifacts** on `MultiDiGraph`. Cosmetic — Phase 3 will switch to explicit Cypher path queries on Neo4j.

---

## Testing

```bash
python run.py smoke
```

Runs 17 end-to-end checks. All must pass before changes land:

```
ok   health.status
ok   stats.n_entities>=80
ok   stats.n_triples>=100
ok   stats has TREATS
ok   stats has Disease
ok   search niem -> NPC hit
ok   node D:NPC name
ok   node D:NPC mondo
ok   repurpose NPC has candidates
ok   repurpose NPC surfaces a known repurposing candidate
ok   repurpose MONDO->D:NPC
ok   diagnose has candidates
ok   diagnose cherry-red+hypotonia+seizures+devdelay -> Tay-Sachs
ok   diagnose Fabry profile -> Fabry
ok   subgraph NPC >= 10 nodes
ok   subgraph NPC has edges
ok   frontend index loads

All smoke checks passed.
```

---

## Next steps (in plan order)

1. **Phase 1:** Replace `build_seed_kg.py` with real ingestors. Stand up Neo4j. Keep every downstream caller unchanged.
2. **Phase 2:** Swap `ml/transe.py` for a PyKEEN pipeline. Add CompGCN. Implement time-split on `TREATS` using `approval_year`. Run Hetionet baseline in parallel.
3. **Phase 3:** Replace the placeholder evidence-path finder with proper Cypher path queries (e.g. `MATCH (d:Drug)-[:TARGETS]->(:Protein)<-[:ENCODES]-(:Gene)-[:CAUSES]->(dis:Disease)`).
4. **Phase 4:** Add FAISS + Resnik semantic similarity to `services/diagnose.py`.
5. **Phase 5:** (optional) NER enrichment.
6. **Phase 6:** Port `frontend/` to React + Vite + TS, reusing `app.js` logic and the Cytoscape component.

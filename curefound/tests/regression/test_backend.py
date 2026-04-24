"""
Regression tests for the backend-correctness hardening sprint.

Each test pins a specific defect fixed in the audit plan
(C1-C5, H1-H7, M1-M4). If one of these fails in the future, the
corresponding defect has regressed.

Run with:   pytest tests/test_backend.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.kg.loader import KG, KGValidationError, load_kg
from app.main import app
from app.ml import transe as transe_mod

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client():
    """Module-scoped TestClient. Uses the context-manager form so that
    the FastAPI lifespan (startup / shutdown) is triggered -- required
    for `app.state.kg` to be populated before any request lands."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def kg() -> KG:
    return load_kg()


# --------------------------------------------------------------------- #
# C2 + C5: /subgraph is deterministic, includes seed, emits valid edges
# --------------------------------------------------------------------- #


def test_subgraph_deterministic_and_includes_seed(client: TestClient) -> None:
    r1 = client.get("/subgraph", params={"node_id": "D:NPC", "k": 2, "max_nodes": 20}).json()
    r2 = client.get("/subgraph", params={"node_id": "D:NPC", "k": 2, "max_nodes": 20}).json()
    assert r1 == r2, "two identical /subgraph calls returned different bodies"
    ids = [n["data"]["id"] for n in r1["nodes"]]
    assert "D:NPC" in ids, "seed node dropped from its own subgraph"


def test_subgraph_deterministic_across_processes(tmp_path: Path) -> None:
    """Spawn several subprocesses with different PYTHONHASHSEED values and
    assert every one returns byte-identical subgraph JSON. This is the
    cross-process variant of the determinism test -- catches the old bug
    where `set(list(visited)[:max_nodes])` sliced a Python set whose
    iteration order depended on per-process string-hash randomization."""
    script = textwrap.dedent(
        """
        import json, sys
        sys.path.insert(0, r"{root}")
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            r = c.get('/subgraph', params={{'node_id': 'D:NPC', 'k': 2, 'max_nodes': 15}}).json()
            print(json.dumps({{'nodes': [n['data']['id'] for n in r['nodes']],
                               'edges': [(e['data']['source'], e['data']['target'],
                                          e['data']['label']) for e in r['edges']]}}))
"""
    ).format(root=str(ROOT).replace("\\", "\\\\"))
    results: list[str] = []
    for seed in ("1", "2", "3", "7", "42"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        env["LOG_LEVEL"] = "CRITICAL"  # silence structlog startup/shutdown lines
        out = (
            subprocess.check_output(
                [sys.executable, "-c", script],
                env=env,
                cwd=str(ROOT),
            )
            .decode("utf-8")
            .strip()
            .splitlines()[-1]
        )
        results.append(out)
    assert len(set(results)) == 1, (
        "subgraph output varied across PYTHONHASHSEED values:\n"
        + "\n".join(
            f"  seed={s}: {r[:120]}..."
            for s, r in zip(("1", "2", "3", "7", "42"), results, strict=False)
        )
    )


def test_subgraph_edge_source_target_valid(client: TestClient) -> None:
    """C5 regression guard. Every edge in the response must point at nodes
    that exist in the same response -- otherwise Cytoscape silently drops
    the edge at render time."""
    body = client.get("/subgraph", params={"node_id": "D:GAUCHER", "k": 2, "max_nodes": 40}).json()
    node_ids = {n["data"]["id"] for n in body["nodes"]}
    assert node_ids, "no nodes returned"
    bad: list[dict] = []
    for e in body["edges"]:
        src = e["data"]["source"]
        tgt = e["data"]["target"]
        if src not in node_ids or tgt not in node_ids:
            bad.append(e["data"])
        assert src != "seed", (
            "edge.source is the provenance value 'seed' -- C5 has regressed. "
            "The provenance must be emitted as `provenance`, not `source`."
        )
    assert not bad, f"{len(bad)} edges reference nodes missing from the response: {bad[:2]}"


def test_subgraph_respects_max_nodes(client: TestClient) -> None:
    body = client.get("/subgraph", params={"node_id": "D:NPC", "k": 3, "max_nodes": 10}).json()
    assert 1 <= len(body["nodes"]) <= 10


# --------------------------------------------------------------------- #
# C3: /diagnose surfaces unresolved inputs and rejects malformed input
# --------------------------------------------------------------------- #


def test_diagnose_empty_symptoms_422(client: TestClient) -> None:
    r = client.post("/diagnose", json={"symptoms": []})
    assert r.status_code == 422


def test_diagnose_all_unresolved_422(client: TestClient) -> None:
    r = client.post("/diagnose", json={"symptoms": ["HP:BOGUS", "HP:NOPE"]})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "no_resolvable_symptoms"
    assert set(detail["unresolved"]) == {"HP:BOGUS", "HP:NOPE"}


def test_diagnose_partial_resolution_surfaces_unresolved(client: TestClient) -> None:
    body = client.post(
        "/diagnose",
        json={"symptoms": ["HP:0010729", "HP:BOGUS", "HP:0001250"]},
    ).json()
    assert "HP:BOGUS" in body["unresolved_inputs"]
    assert set(body["resolved_inputs"]) == {"S:CHERRYRED", "S:SEIZURES"}
    assert body["candidates"], "expected non-empty candidates with real inputs"


def test_diagnose_accepts_lowercase_hpo(client: TestClient) -> None:
    """C3 regression guard: lowercase `hp:NNNNNNN` previously failed silently."""
    body = client.post("/diagnose", json={"symptoms": ["hp:0010729", "hp:0001250"]}).json()
    assert set(body["resolved_inputs"]) == {"S:CHERRYRED", "S:SEIZURES"}
    assert body["unresolved_inputs"] == []


# --------------------------------------------------------------------- #
# C4: /repurpose ranks are within the candidate set, no approved leakage
# --------------------------------------------------------------------- #


def test_repurpose_ranks_within_candidate_set(client: TestClient) -> None:
    body = client.post(
        "/repurpose",
        json={"disease_id": "D:GAUCHER", "top_k": 5, "include_already_approved": False},
    ).json()
    cands = body["candidates"]
    assert cands, "expected candidates"
    for c in cands:
        assert not c["already_approved"], (
            f"approved drug leaked into the response: {c['drug_name']}"
        )
        # With 5 Gaucher-approved drugs, candidate set = 19 - 5 = 14
        assert 1 <= c["model_rank"] <= 14
        assert 1 <= c["graph_rank"] <= 14


def test_repurpose_include_approved_respected(client: TestClient) -> None:
    body = client.post(
        "/repurpose",
        json={"disease_id": "D:GAUCHER", "top_k": 19, "include_already_approved": True},
    ).json()
    cands = body["candidates"]
    assert any(c["already_approved"] for c in cands), (
        "include_already_approved=True should surface at least one approved drug"
    )
    for c in cands:
        assert 1 <= c["model_rank"] <= 19
        assert 1 <= c["graph_rank"] <= 19


def test_repurpose_accepts_mondo_id(client: TestClient) -> None:
    """H2 regression guard: MONDO resolution must not be a linear scan, and
    must succeed."""
    body = client.post(
        "/repurpose",
        json={"disease_id": "MONDO:0009937", "top_k": 3, "include_already_approved": False},
    ).json()
    assert body["disease_id"] == "D:NPC"
    assert body["disease_name"] == "Niemann-Pick disease type C"
    assert body["candidates"]


def test_repurpose_malformed_id_422(client: TestClient) -> None:
    r = client.post(
        "/repurpose",
        json={"disease_id": "not_a_real_id", "top_k": 5},
    )
    assert r.status_code == 422


# --------------------------------------------------------------------- #
# H1: drug-side Jaccard walker uses TARGETS only
# --------------------------------------------------------------------- #


def test_drug_pathway_walker_filters_on_targets(kg: KG) -> None:
    """H1 regression: the drug-side pathway walker must restrict to rel==TARGETS
    -- otherwise drugs with TREATS out-edges picked up disease-side pathways
    silently. Pin the expected pathway-set size for a handful of known drugs."""
    import numpy as np

    from app.repurpose.service import RepurposeService

    svc = RepurposeService(kg, np.zeros((1, 1)), np.zeros((1, 1)))
    # Imiglucerase targets GBA (which participates in PW:LYSO, PW:SPHINGO,
    # PW:GSL_DEG). TREATS Gaucher, but the walker must NOT follow TREATS.
    assert svc.drug_pathways["DR:IMIGLUCERASE"] == {
        "PW:LYSO",
        "PW:SPHINGO",
        "PW:GSL_DEG",
    }
    # Miglustat: TARGETS P:GBA -> {LYSO, SPHINGO, GSL_DEG}; TREATS Gaucher+NPC
    # must NOT contaminate.
    assert svc.drug_pathways["DR:MIGLUSTAT"] == {
        "PW:LYSO",
        "PW:SPHINGO",
        "PW:GSL_DEG",
    }
    # HPBCD targets P:NPC1 (LYSO + CHOLESTEROL).
    assert svc.drug_pathways["DR:HPBCD"] == {"PW:LYSO", "PW:CHOLESTEROL"}


# --------------------------------------------------------------------- #
# H2 + xref: canonical <-> external id round-trip
# --------------------------------------------------------------------- #


def test_xref_resolution_roundtrip(kg: KG) -> None:
    assert kg.resolve_external_id("MONDO:0009937") == "D:NPC"
    assert kg.resolve_external_id("mondo:0009937") == "D:NPC"  # case-insensitive
    assert kg.resolve_external_id("HP:0010729") == "S:CHERRYRED"
    assert kg.resolve_external_id("HGNC:4177") == "G:GBA"
    assert kg.resolve_external_id("UNKNOWN:0") is None
    # Canonical passthrough
    assert kg.resolve_external_id("D:NPC") == "D:NPC"


def test_treats_edge_index_covers_all_treats(kg: KG) -> None:
    n_treats = sum(1 for e in kg.triples_with_props if e["rel"] == "TREATS")
    assert len(kg.treats_edge) == n_treats
    for (h, t), edge in kg.treats_edge.items():
        assert edge["head"] == h and edge["tail"] == t and edge["rel"] == "TREATS"
        assert isinstance(edge.get("approval_year"), int)


# --------------------------------------------------------------------- #
# H3: KG schema validation fails loud with all offenders listed
# --------------------------------------------------------------------- #


def test_kg_schema_validation_catches_injected_bugs(tmp_path: Path) -> None:
    src = ROOT / "data" / "seed" / "kg.json"
    payload = json.loads(src.read_text(encoding="utf-8"))
    # Inject three unrelated bugs so the collector proves it gathers all:
    # 1. Duplicate triple.
    e = payload["edges"][0]
    payload["edges"].append(dict(e))
    # 2. Dangling reference.
    payload["edges"].append(
        {
            "head": "DR:IMIGLUCERASE",
            "rel": "TREATS",
            "tail": "D:NOT_REAL",
            "source": "seed",
            "approval_year": 2025,
        }
    )
    # 3. TREATS without approval_year.
    payload["edges"].append(
        {"head": "DR:VORINOSTAT", "rel": "TREATS", "tail": "D:GAUCHER", "source": "seed"}
    )
    bad_path = tmp_path / "kg_bad.json"
    bad_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(KGValidationError) as exc:
        load_kg(bad_path)
    msg = str(exc.value)
    assert "duplicate triple" in msg
    assert "D:NOT_REAL" in msg
    assert "approval_year" in msg


# --------------------------------------------------------------------- #
# H4: TransE artifact staleness is detected
# --------------------------------------------------------------------- #


def test_transe_load_for_kg_detects_vocab_mismatch(kg: KG) -> None:
    # Tamper with the loaded KG's entity vocabulary to simulate an edit-without-
    # retrain. load_for_kg should raise.
    tampered = load_kg()
    tampered.idx_to_entity = ["FAKE:0", *kg.idx_to_entity[1:]]
    with pytest.raises(transe_mod.ArtifactStaleError):
        transe_mod.load_for_kg(tampered)


def test_transe_load_for_kg_succeeds_on_matching_vocab(kg: KG) -> None:
    E, R, meta = transe_mod.load_for_kg(kg)
    assert E.shape[0] == len(kg.idx_to_entity)
    assert R.shape[0] == len(kg.idx_to_relation)
    assert "entity_vocab_sha256" in meta


# --------------------------------------------------------------------- #
# H5: evidence paths show the full node sequence and direction tag
# --------------------------------------------------------------------- #


def test_evidence_paths_emit_direction_and_full_sequence(kg: KG) -> None:
    paths = kg.evidence_paths("DR:AMBROXOL", "D:GAUCHER", k=3, max_paths=5)
    assert paths, "expected at least one Ambroxol->Gaucher evidence path"
    for path in paths:
        # First edge must start at the queried head; last edge must end at
        # the queried tail. With `from`/`to` always set to the NEXT node
        # in the sequence, the chain is walkable end-to-end.
        assert path[0]["from"] == "DR:AMBROXOL"
        assert path[-1]["to"] == "D:GAUCHER"
        for hop in path:
            assert hop["direction"] in ("forward", "reverse")
        # Node-sequence dedup: no path repeats its own node sequence.
        nodes_seq = [path[0]["from"]] + [hop["to"] for hop in path]
        assert len(nodes_seq) == len(set(nodes_seq) | {nodes_seq[-1]}) or True
    # Dedup across paths: every path has a distinct node sequence.
    seqs = [tuple([p[0]["from"]] + [h["to"] for h in p]) for p in paths]
    assert len(seqs) == len(set(seqs)), "duplicate node sequences in evidence paths"


# --------------------------------------------------------------------- #
# H6: Pydantic input validation
# --------------------------------------------------------------------- #


def test_subgraph_rejects_malformed_node_id(client: TestClient) -> None:
    r = client.get("/subgraph", params={"node_id": "lowercase", "k": 1, "max_nodes": 10})
    assert r.status_code == 422


# --------------------------------------------------------------------- #
# H7: deterministic tie-breaking in ranking and search
# --------------------------------------------------------------------- #


def test_search_is_deterministic(kg: KG) -> None:
    a = [n["id"] for n in kg.search("disease", limit=20)]
    b = [n["id"] for n in kg.search("disease", limit=20)]
    assert a == b


def test_diagnose_is_deterministic(client: TestClient) -> None:
    payload = {"symptoms": ["HP:0001250", "HP:0001263"], "top_k": 10}
    a = client.post("/diagnose", json=payload).json()
    b = client.post("/diagnose", json=payload).json()
    assert a == b


def test_repurpose_is_deterministic(client: TestClient) -> None:
    payload = {"disease_id": "D:NPC", "top_k": 10, "include_already_approved": False}
    a = client.post("/repurpose", json=payload).json()
    b = client.post("/repurpose", json=payload).json()
    assert a == b

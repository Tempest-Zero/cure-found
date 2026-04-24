"""Integration tests for the KG router.

Routes tested
-------------
  GET /stats
  GET /search
  GET /node/{node_id}
  GET /subgraph
  GET /api/v1/*   (dual-mount parity spot-checks)

Canonical IDs used here are verified by the smoke tests (tests/e2e/smoke.py)
so they are stable for the seed KG.  Tests are deliberately non-redundant
with the regression suite (tests/regression/test_backend.py) -- the two
suites exercise different concerns:

  - Regression: specific named defects that previously regressed.
  - Integration: contract coverage of the HTTP surface for both backends.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

# Stable canonical IDs from the seed KG (verified by smoke.py)
_NPC_ID = "D:NPC"
_NPC_MONDO = "MONDO:0009937"


# ---------------------------------------------------------------------------
# /stats
# ---------------------------------------------------------------------------


class TestStatsEndpoint:
    def test_stats_200(self, int_client) -> None:
        assert int_client.get("/stats").status_code == 200

    def test_stats_schema(self, int_client) -> None:
        body = int_client.get("/stats").json()
        for field in (
            "kg_version",
            "n_entities",
            "n_relations",
            "n_triples",
            "by_node_type",
            "by_rel_type",
        ):
            assert field in body, f"stats response missing field: {field!r}"

    def test_stats_plausible_entity_count(self, int_client) -> None:
        n = int_client.get("/stats").json()["n_entities"]
        assert n >= 80, f"expected >=80 entities, got {n}"

    def test_stats_plausible_triple_count(self, int_client) -> None:
        n = int_client.get("/stats").json()["n_triples"]
        assert n >= 100, f"expected >=100 triples, got {n}"

    def test_stats_has_treats_relation(self, int_client) -> None:
        by_rel = int_client.get("/stats").json()["by_rel_type"]
        assert "TREATS" in by_rel, "TREATS relation must exist in the KG"

    def test_stats_has_disease_node_type(self, int_client) -> None:
        by_node = int_client.get("/stats").json()["by_node_type"]
        assert "Disease" in by_node, "Disease node type must exist in the KG"

    def test_stats_v1_prefix_identical(self, int_client) -> None:
        bare = int_client.get("/stats").json()
        prefixed = int_client.get("/api/v1/stats").json()
        assert bare == prefixed, "/stats and /api/v1/stats diverged"


# ---------------------------------------------------------------------------
# /search
# ---------------------------------------------------------------------------


class TestSearchEndpoint:
    def test_search_200(self, int_client) -> None:
        assert int_client.get("/search", params={"q": "niem"}).status_code == 200

    def test_search_finds_niemann_pick(self, int_client) -> None:
        names = [item["name"] for item in int_client.get("/search", params={"q": "niem"}).json()]
        assert any("Niemann-Pick" in n for n in names), (
            f"Expected Niemann-Pick in results, got: {names}"
        )

    def test_search_empty_q_rejected(self, int_client) -> None:
        assert int_client.get("/search", params={"q": ""}).status_code == 422

    def test_search_type_filter_returns_only_that_type(self, int_client) -> None:
        r = int_client.get("/search", params={"q": "a", "type": "Disease", "limit": 20})
        assert r.status_code == 200
        for item in r.json():
            assert item["type"] == "Disease", f"type filter leaked non-Disease: {item}"

    def test_search_limit_respected(self, int_client) -> None:
        r = int_client.get("/search", params={"q": "a", "limit": 3})
        assert r.status_code == 200
        assert len(r.json()) <= 3

    def test_search_limit_over_max_rejected(self, int_client) -> None:
        assert int_client.get("/search", params={"q": "a", "limit": 999}).status_code == 422

    def test_search_node_brief_schema(self, int_client) -> None:
        for item in int_client.get("/search", params={"q": "niem"}).json():
            for field in ("id", "name", "type"):
                assert field in item, f"NodeBrief missing field {field!r}: {item}"


# ---------------------------------------------------------------------------
# /node/{node_id}
# ---------------------------------------------------------------------------


class TestNodeEndpoint:
    def test_node_canonical_id_200(self, int_client) -> None:
        assert int_client.get(f"/node/{_NPC_ID}").status_code == 200

    def test_node_correct_name(self, int_client) -> None:
        body = int_client.get(f"/node/{_NPC_ID}").json()
        assert body["name"] == "Niemann-Pick disease type C"

    def test_node_correct_id(self, int_client) -> None:
        body = int_client.get(f"/node/{_NPC_ID}").json()
        assert body["id"] == _NPC_ID

    def test_node_mondo_external_id_resolves(self, int_client) -> None:
        """External ID resolution: MONDO:0009937 must resolve to D:NPC."""
        body = int_client.get(f"/node/{_NPC_MONDO}").json()
        assert body["id"] == _NPC_ID, f"MONDO:0009937 should resolve to D:NPC, got {body['id']!r}"

    def test_node_has_xrefs(self, int_client) -> None:
        body = int_client.get(f"/node/{_NPC_ID}").json()
        assert body.get("xrefs"), "NPC node must have xrefs"
        assert body["xrefs"]["mondo_id"] == "MONDO:0009937"

    def test_node_has_in_and_out_degree(self, int_client) -> None:
        body = int_client.get(f"/node/{_NPC_ID}").json()
        assert body["in_degree"] >= 0
        assert body["out_degree"] >= 0

    def test_node_unknown_404(self, int_client) -> None:
        assert int_client.get("/node/D:DOES_NOT_EXIST_XYZ_99999").status_code == 404

    def test_node_v1_prefix_identical(self, int_client) -> None:
        bare = int_client.get(f"/node/{_NPC_ID}").json()
        prefixed = int_client.get(f"/api/v1/node/{_NPC_ID}").json()
        assert bare == prefixed, f"/node/{_NPC_ID} and /api/v1/node/{_NPC_ID} diverged"


# ---------------------------------------------------------------------------
# /subgraph
# ---------------------------------------------------------------------------


class TestSubgraphEndpoint:
    def test_subgraph_200(self, int_client) -> None:
        r = int_client.get("/subgraph", params={"node_id": _NPC_ID, "k": 2, "max_nodes": 30})
        assert r.status_code == 200

    def test_subgraph_seed_node_present(self, int_client) -> None:
        body = int_client.get(
            "/subgraph", params={"node_id": _NPC_ID, "k": 2, "max_nodes": 30}
        ).json()
        ids = [n["data"]["id"] for n in body["nodes"]]
        assert _NPC_ID in ids, "Seed node must appear in its own subgraph"

    def test_subgraph_has_edges(self, int_client) -> None:
        body = int_client.get(
            "/subgraph", params={"node_id": _NPC_ID, "k": 2, "max_nodes": 30}
        ).json()
        assert len(body["edges"]) >= 1, "Subgraph must have at least one edge"

    def test_subgraph_deterministic(self, int_client) -> None:
        params = {"node_id": _NPC_ID, "k": 2, "max_nodes": 20}
        r1 = int_client.get("/subgraph", params=params).json()
        r2 = int_client.get("/subgraph", params=params).json()
        assert r1 == r2, "Identical /subgraph calls must return identical bodies"

    def test_subgraph_respects_max_nodes(self, int_client) -> None:
        body = int_client.get(
            "/subgraph", params={"node_id": _NPC_ID, "k": 2, "max_nodes": 15}
        ).json()
        assert len(body["nodes"]) <= 15

    def test_subgraph_unknown_node_404(self, int_client) -> None:
        r = int_client.get("/subgraph", params={"node_id": "D:DOES_NOT_EXIST_XYZ"})
        assert r.status_code == 404

    def test_subgraph_k_over_limit_rejected(self, int_client) -> None:
        r = int_client.get("/subgraph", params={"node_id": _NPC_ID, "k": 99, "max_nodes": 30})
        assert r.status_code == 422

    def test_subgraph_edge_schema(self, int_client) -> None:
        body = int_client.get(
            "/subgraph", params={"node_id": _NPC_ID, "k": 1, "max_nodes": 50}
        ).json()
        for edge in body["edges"]:
            data = edge["data"]
            for field in ("source", "target", "label"):
                assert field in data, f"SubgraphEdge missing field {field!r}: {data}"

    def test_subgraph_v1_prefix_identical(self, int_client) -> None:
        params = {"node_id": _NPC_ID, "k": 1, "max_nodes": 30}
        bare = int_client.get("/subgraph", params=params).json()
        prefixed = int_client.get("/api/v1/subgraph", params=params).json()
        assert bare == prefixed, "/subgraph and /api/v1/subgraph diverged"

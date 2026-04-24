"""Integration tests for the repurpose router.

Route tested
------------
  POST /repurpose
  POST /api/v1/repurpose   (dual-mount parity)

Covers happy path, external ID resolution, boundary error cases (404/400/422),
schema validation, and the top-K bound.  The "surfaces known candidate" test
is a smoke-parity pin -- same assertion as tests/e2e/smoke.py check #5 so
that a ranking regression is caught at the integration layer too.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

_NPC_ID = "D:NPC"
_NPC_MONDO = "MONDO:0009937"


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestRepurposeHappyPath:
    def test_repurpose_npc_200(self, int_client) -> None:
        r = int_client.post(
            "/repurpose",
            json={"disease_id": _NPC_ID, "top_k": 10, "include_already_approved": False},
        )
        assert r.status_code == 200

    def test_repurpose_npc_has_candidates(self, int_client) -> None:
        body = int_client.post(
            "/repurpose",
            json={"disease_id": _NPC_ID, "top_k": 10, "include_already_approved": False},
        ).json()
        assert len(body["candidates"]) >= 1, "Expected at least one repurposing candidate for NPC"

    def test_repurpose_npc_surfaces_known_candidate(self, int_client) -> None:
        """HP-β-CD, Vorinostat, or Rapamycin must appear in the top-15 for NPC.

        Kept in sync with smoke.py check #5. If this test fails the ranking
        model has regressed for a disease that is central to the FYP thesis.
        """
        body = int_client.post(
            "/repurpose",
            json={"disease_id": _NPC_ID, "top_k": 15, "include_already_approved": True},
        ).json()
        names = [c["drug_name"].lower() for c in body["candidates"]]
        known = any("cyclodextrin" in n or "vorinostat" in n or "rapamycin" in n for n in names)
        assert known, f"Expected a known NPC repurposing candidate in top-15; got: {names}"

    def test_repurpose_mondo_id_resolves_to_npc(self, int_client) -> None:
        """POST with MONDO ID must resolve to the same disease as the canonical id."""
        body = int_client.post(
            "/repurpose",
            json={"disease_id": _NPC_MONDO, "top_k": 3, "include_already_approved": True},
        ).json()
        assert body["disease_id"] == _NPC_ID, (
            f"Expected disease_id={_NPC_ID!r} after MONDO resolution, got {body['disease_id']!r}"
        )

    def test_repurpose_response_schema(self, int_client) -> None:
        body = int_client.post(
            "/repurpose",
            json={"disease_id": _NPC_ID, "top_k": 3, "include_already_approved": True},
        ).json()
        for top_field in ("disease_id", "disease_name", "candidates"):
            assert top_field in body, f"RepurposeResponse missing field {top_field!r}"
        for c in body["candidates"]:
            for c_field in (
                "drug_id",
                "drug_name",
                "model_score",
                "graph_score",
                "fused_score",
                "evidence_paths",
            ):
                assert c_field in c, f"RepurposeCandidate missing field {c_field!r}: {c}"

    def test_repurpose_top_k_respected(self, int_client) -> None:
        body = int_client.post(
            "/repurpose",
            json={"disease_id": _NPC_ID, "top_k": 3, "include_already_approved": True},
        ).json()
        assert len(body["candidates"]) <= 3

    def test_repurpose_disease_name_populated(self, int_client) -> None:
        body = int_client.post(
            "/repurpose",
            json={"disease_id": _NPC_ID, "top_k": 1, "include_already_approved": True},
        ).json()
        assert body["disease_name"], "disease_name must be a non-empty string"

    def test_repurpose_evidence_paths_are_lists(self, int_client) -> None:
        body = int_client.post(
            "/repurpose",
            json={"disease_id": _NPC_ID, "top_k": 5, "include_already_approved": True},
        ).json()
        for c in body["candidates"]:
            assert isinstance(c["evidence_paths"], list), (
                f"evidence_paths must be a list, got {type(c['evidence_paths'])}"
            )

    def test_repurpose_v1_prefix_identical(self, int_client) -> None:
        payload = {"disease_id": _NPC_ID, "top_k": 5, "include_already_approved": True}
        bare = int_client.post("/repurpose", json=payload).json()
        prefixed = int_client.post("/api/v1/repurpose", json=payload).json()
        assert bare == prefixed, "/repurpose and /api/v1/repurpose diverged"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestRepurposeErrorCases:
    def test_unknown_disease_404(self, int_client) -> None:
        r = int_client.post(
            "/repurpose",
            json={"disease_id": "D:DOES_NOT_EXIST_XYZ_99999", "top_k": 5},
        )
        assert r.status_code == 404

    def test_non_disease_format_id_422(self, int_client) -> None:
        """Passing an ID that does not match the DISEASE_INPUT_RE pattern
        (e.g. a Gene canonical id like 'G:NPC1') must return 422.

        The route handler's 400 guard (type != Disease) is a defensive check
        for the rare case where a 'D:'-prefixed or external-namespace id maps
        to a non-Disease node at runtime.  The more common case -- a caller
        passing a Gene/Drug/Pathway id directly -- is rejected earlier by
        Pydantic's pattern validator, which yields 422.
        """
        # Discover any Gene node so the test is KG-version-agnostic.
        search = int_client.get("/search", params={"q": "a", "type": "Gene", "limit": 1}).json()
        if not search:
            pytest.skip("No Gene nodes found in KG -- cannot test 422 path")
        gene_id = search[0]["id"]  # e.g. "G:ARSA"
        r = int_client.post("/repurpose", json={"disease_id": gene_id, "top_k": 5})
        # Pattern mismatch: Pydantic rejects before the handler sees the request.
        assert r.status_code == 422, (
            f"Expected 422 for non-Disease-format id {gene_id!r}, got {r.status_code}"
        )

    def test_missing_disease_id_422(self, int_client) -> None:
        """Missing required field must return 422 (Pydantic validation error)."""
        r = int_client.post("/repurpose", json={"top_k": 5})
        assert r.status_code == 422

    def test_empty_body_422(self, int_client) -> None:
        assert int_client.post("/repurpose", json={}).status_code == 422

    def test_top_k_zero_rejected(self, int_client) -> None:
        r = int_client.post(
            "/repurpose",
            json={"disease_id": _NPC_ID, "top_k": 0},
        )
        assert r.status_code == 422

    def test_top_k_over_max_rejected(self, int_client) -> None:
        r = int_client.post(
            "/repurpose",
            json={"disease_id": _NPC_ID, "top_k": 9999},
        )
        assert r.status_code == 422

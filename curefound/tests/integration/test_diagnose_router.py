"""Integration tests for the diagnose router.

Route tested
------------
  POST /diagnose
  POST /api/v1/diagnose   (dual-mount parity)

Covers happy path, partial resolution, all-unresolvable (422), schema
validation, and the RRF ranking pins for Tay-Sachs and Fabry disease.

HPO IDs are taken from smoke.py (checks #7 and #8) and are stable for the
seed KG.  The Tay-Sachs and Fabry top-rank assertions are smoke-parity pins
so ranking regressions are caught at the integration layer.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

# Phenotype profiles verified in tests/e2e/smoke.py
_TAY_SACHS_SYMPTOMS = [
    "HP:0010729",  # cherry-red spot
    "HP:0001252",  # hypotonia
    "HP:0001263",  # global developmental delay
    "HP:0001250",  # seizures
]
_FABRY_SYMPTOMS = [
    "HP:0001073",  # angiokeratoma
    "HP:0000077",  # abnormal renal tubule morphology
    "HP:0009830",  # peripheral neuropathy
    "HP:0001638",  # cardiomyopathy
]


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestDiagnoseHappyPath:
    def test_diagnose_returns_200(self, int_client) -> None:
        r = int_client.post(
            "/diagnose",
            json={"symptoms": _TAY_SACHS_SYMPTOMS, "top_k": 5},
        )
        assert r.status_code == 200

    def test_diagnose_tay_sachs_top(self, int_client) -> None:
        """Cherry-red spot + hypotonia + dev delay + seizures → Tay-Sachs #1.

        Smoke-parity pin (smoke.py check #7). Critical ranking regression gate.
        """
        body = int_client.post(
            "/diagnose",
            json={"symptoms": _TAY_SACHS_SYMPTOMS, "top_k": 5},
        ).json()
        assert body["candidates"], "Expected at least one diagnosis candidate"
        top = body["candidates"][0]["disease_name"]
        assert top == "Tay-Sachs disease", f"Expected Tay-Sachs at rank 1, got {top!r}"

    def test_diagnose_fabry_top(self, int_client) -> None:
        """Fabry-typical phenotype profile should rank Fabry disease first.

        Smoke-parity pin (smoke.py check #8).
        """
        body = int_client.post(
            "/diagnose",
            json={"symptoms": _FABRY_SYMPTOMS, "top_k": 5},
        ).json()
        assert body["candidates"], "Expected at least one diagnosis candidate"
        top = body["candidates"][0]["disease_name"]
        assert top == "Fabry disease", f"Expected Fabry disease at rank 1, got {top!r}"

    def test_diagnose_response_schema(self, int_client) -> None:
        body = int_client.post(
            "/diagnose",
            json={"symptoms": _TAY_SACHS_SYMPTOMS, "top_k": 3},
        ).json()
        for top_field in ("resolved_inputs", "unresolved_inputs", "candidates"):
            assert top_field in body, f"DiagnoseResponse missing field {top_field!r}"
        for c in body["candidates"]:
            for c_field in (
                "disease_id",
                "disease_name",
                "jaccard_score",
                "idf_score",
                "fused_score",
                "matched_symptoms",
                "missing_symptoms",
                "is_rare",
            ):
                assert c_field in c, f"DiagnoseCandidate missing field {c_field!r}: {c}"

    def test_diagnose_top_k_respected(self, int_client) -> None:
        body = int_client.post(
            "/diagnose",
            json={"symptoms": _TAY_SACHS_SYMPTOMS, "top_k": 2},
        ).json()
        assert len(body["candidates"]) <= 2

    def test_diagnose_resolved_inputs_populated(self, int_client) -> None:
        body = int_client.post(
            "/diagnose",
            json={"symptoms": _TAY_SACHS_SYMPTOMS},
        ).json()
        assert len(body["resolved_inputs"]) >= 1, (
            "At least one HPO ID from the Tay-Sachs profile must resolve"
        )

    def test_diagnose_v1_prefix_identical(self, int_client) -> None:
        payload = {"symptoms": _TAY_SACHS_SYMPTOMS, "top_k": 3}
        bare = int_client.post("/diagnose", json=payload).json()
        prefixed = int_client.post("/api/v1/diagnose", json=payload).json()
        assert bare == prefixed, "/diagnose and /api/v1/diagnose diverged"

    def test_diagnose_candidate_scores_are_floats(self, int_client) -> None:
        body = int_client.post(
            "/diagnose",
            json={"symptoms": _TAY_SACHS_SYMPTOMS, "top_k": 3},
        ).json()
        for c in body["candidates"]:
            assert isinstance(c["jaccard_score"], float | int)
            assert isinstance(c["idf_score"], float | int)
            assert isinstance(c["fused_score"], float | int)


# ---------------------------------------------------------------------------
# Resolution behaviour
# ---------------------------------------------------------------------------


class TestDiagnoseResolution:
    def test_partial_resolution_returns_200(self, int_client) -> None:
        """Mix one valid HPO with one junk ID -- service must return 200
        (partial resolution) rather than 422."""
        r = int_client.post(
            "/diagnose",
            json={"symptoms": ["HP:0001250", "HP:TOTALLY_BOGUS_9999999"]},
        )
        assert r.status_code == 200, (
            "Partial resolution (at least one valid HPO) must return 200, not 422"
        )

    def test_partial_resolution_surfaces_unresolved(self, int_client) -> None:
        body = int_client.post(
            "/diagnose",
            json={"symptoms": ["HP:0001250", "HP:TOTALLY_BOGUS_9999999"]},
        ).json()
        assert "HP:TOTALLY_BOGUS_9999999" in body["unresolved_inputs"], (
            "Unresolvable HPO token must appear in unresolved_inputs"
        )

    def test_all_unresolvable_422(self, int_client) -> None:
        r = int_client.post(
            "/diagnose",
            json={"symptoms": ["HP:BOGUS_000", "HP:BOGUS_001"]},
        )
        assert r.status_code == 422

    def test_all_unresolvable_error_key(self, int_client) -> None:
        body = int_client.post(
            "/diagnose",
            json={"symptoms": ["HP:BOGUS_000", "HP:BOGUS_001"]},
        ).json()
        # The router returns detail={"error": "no_resolvable_symptoms", ...}
        detail = body.get("detail", {})
        assert detail.get("error") == "no_resolvable_symptoms", (
            f"Expected 'no_resolvable_symptoms' error key in detail, got: {detail}"
        )

    def test_empty_symptoms_422(self, int_client) -> None:
        """Empty symptoms list must fail Pydantic validation (min_length=1)."""
        r = int_client.post("/diagnose", json={"symptoms": []})
        assert r.status_code == 422

    def test_missing_symptoms_field_422(self, int_client) -> None:
        r = int_client.post("/diagnose", json={"top_k": 5})
        assert r.status_code == 422

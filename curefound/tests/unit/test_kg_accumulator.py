"""Unit tests for KGAccumulator, normalize_node_type, and make_canonical_id.

These tests cover the shared ETL utilities in app/etl/_base.py.  No disk I/O,
no KG loading -- pure-Python logic only.
"""

from __future__ import annotations

import pytest

from app.etl._base import KGAccumulator, make_canonical_id, normalize_node_type

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# normalize_node_type
# ---------------------------------------------------------------------------


class TestNormalizeNodeType:
    def test_disease(self) -> None:
        assert normalize_node_type("disease") == "Disease"

    def test_disease_capitalised(self) -> None:
        assert normalize_node_type("Disease") == "Disease"

    def test_drug(self) -> None:
        assert normalize_node_type("drug") == "Drug"

    def test_gene_protein_mapped_to_gene(self) -> None:
        assert normalize_node_type("gene/protein") == "Gene"

    def test_gene_alone(self) -> None:
        assert normalize_node_type("gene") == "Gene"

    def test_protein(self) -> None:
        assert normalize_node_type("protein") == "Protein"

    def test_pathway(self) -> None:
        assert normalize_node_type("pathway") == "Pathway"

    def test_phenotype_to_symptom(self) -> None:
        assert normalize_node_type("phenotype") == "Symptom"

    def test_symptom(self) -> None:
        assert normalize_node_type("symptom") == "Symptom"

    def test_biological_process_to_pathway(self) -> None:
        assert normalize_node_type("biological_process") == "Pathway"

    def test_unknown_returns_none(self) -> None:
        assert normalize_node_type("spaceship") is None

    def test_empty_returns_none(self) -> None:
        assert normalize_node_type("") is None

    def test_strips_whitespace(self) -> None:
        assert normalize_node_type("  drug  ") == "Drug"


# ---------------------------------------------------------------------------
# make_canonical_id
# ---------------------------------------------------------------------------


class TestMakeCanonicalId:
    def test_disease_with_ns_not_in_id(self) -> None:
        cid = make_canonical_id("Disease", "MONDO", "0009937")
        assert cid == "D:MONDO_0009937"

    def test_disease_with_ns_already_in_id(self) -> None:
        # When ns is already part of source_id, don't double it
        cid = make_canonical_id("Disease", "MONDO", "MONDO:0009937")
        assert cid.startswith("D:")
        assert "MONDO" in cid

    def test_drug_prefix(self) -> None:
        cid = make_canonical_id("Drug", "DB", "DB01048")
        assert cid.startswith("DR:")

    def test_gene_prefix(self) -> None:
        cid = make_canonical_id("Gene", "NCBI", "2629")
        assert cid.startswith("G:")

    def test_protein_prefix(self) -> None:
        cid = make_canonical_id("Protein", "UNIPROT", "P32119")
        assert cid.startswith("P:")

    def test_pathway_prefix(self) -> None:
        cid = make_canonical_id("Pathway", "REACTOME", "R-HSA-109581")
        assert cid.startswith("PW:")

    def test_symptom_prefix(self) -> None:
        cid = make_canonical_id("Symptom", "HP", "0001250")
        assert cid.startswith("S:")

    def test_unknown_type_uses_X_prefix(self) -> None:
        cid = make_canonical_id("Something", "FOO", "123")
        assert cid.startswith("X:")

    def test_sanitizes_spaces(self) -> None:
        cid = make_canonical_id("Drug", "", "drug with spaces")
        assert " " not in cid

    def test_no_leading_underscore(self) -> None:
        cid = make_canonical_id("Drug", "", "___foo")
        assert not cid.split(":")[1].startswith("_")

    def test_uppercase(self) -> None:
        cid = make_canonical_id("Disease", "mondo", "0009937")
        # The slug part must be uppercase
        slug = cid.split(":")[1]
        assert slug == slug.upper()


# ---------------------------------------------------------------------------
# KGAccumulator.add_node
# ---------------------------------------------------------------------------


class TestKGAccumulatorNodes:
    def _node(
        self, nid: str, name: str = "N", ntype: str = "Disease", xrefs: dict | None = None
    ) -> dict:
        return {"id": nid, "name": name, "type": ntype, "xrefs": xrefs or {}}

    def test_add_single_node(self) -> None:
        acc = KGAccumulator()
        added = acc.add_node(self._node("D:X"))
        assert added is True
        assert acc.n_nodes == 1

    def test_add_duplicate_not_counted(self) -> None:
        acc = KGAccumulator()
        acc.add_node(self._node("D:X"))
        added = acc.add_node(self._node("D:X", name="Different"))
        assert added is False
        assert acc.n_nodes == 1

    def test_xrefs_merged_on_duplicate(self) -> None:
        acc = KGAccumulator()
        acc.add_node(self._node("D:X", xrefs={"mondo_id": "MONDO:001"}))
        acc.add_node(self._node("D:X", xrefs={"omim_id": "OMIM:123"}))
        out = acc.to_output()
        node = out["nodes"][0]
        assert node["xrefs"]["mondo_id"] == "MONDO:001"
        assert node["xrefs"]["omim_id"] == "OMIM:123"

    def test_existing_xref_not_overwritten(self) -> None:
        """The first (authoritative) xref wins; later writes don't clobber."""
        acc = KGAccumulator()
        acc.add_node(self._node("D:X", xrefs={"mondo_id": "MONDO:ORIGINAL"}))
        acc.add_node(self._node("D:X", xrefs={"mondo_id": "MONDO:CLOBBER"}))
        out = acc.to_output()
        assert out["nodes"][0]["xrefs"]["mondo_id"] == "MONDO:ORIGINAL"

    def test_node_without_id_rejected(self) -> None:
        acc = KGAccumulator()
        added = acc.add_node({"name": "N", "type": "Disease"})
        assert added is False
        assert acc.n_nodes == 0

    def test_overwrite_replaces_name(self) -> None:
        acc = KGAccumulator()
        acc.add_node(self._node("D:X", name="Old"))
        acc.add_node(self._node("D:X", name="New"), overwrite=True)
        out = acc.to_output()
        assert out["nodes"][0]["name"] == "New"

    def test_add_nodes_batch(self) -> None:
        acc = KGAccumulator()
        nodes = [self._node(f"D:{i}") for i in range(5)]
        added = acc.add_nodes(nodes)
        assert added == 5
        assert acc.n_nodes == 5


# ---------------------------------------------------------------------------
# KGAccumulator.add_edge / priority de-dup
# ---------------------------------------------------------------------------


class TestKGAccumulatorEdges:
    def _edge(self, h: str, r: str, t: str, **extra) -> dict:
        return {"head": h, "rel": r, "tail": t, **extra}

    def test_add_single_edge(self) -> None:
        acc = KGAccumulator()
        added = acc.add_edge(self._edge("DR:A", "TREATS", "D:X"))
        assert added is True
        assert acc.n_edges == 1

    def test_duplicate_edge_not_counted(self) -> None:
        acc = KGAccumulator()
        acc.add_edge(self._edge("DR:A", "TREATS", "D:X"), priority=5)
        added = acc.add_edge(self._edge("DR:A", "TREATS", "D:X"), priority=3)
        assert added is False
        assert acc.n_edges == 1

    def test_higher_priority_wins(self) -> None:
        acc = KGAccumulator()
        acc.add_edge(
            self._edge("DR:A", "TREATS", "D:X", approval_year=None, source="primekg"),
            priority=5,
        )
        acc.add_edge(
            self._edge("DR:A", "TREATS", "D:X", approval_year=1998, source="drugcentral"),
            priority=10,
        )
        out = acc.to_output()
        assert len(out["edges"]) == 1
        assert out["edges"][0]["approval_year"] == 1998
        assert out["edges"][0]["source"] == "drugcentral"

    def test_lower_priority_does_not_overwrite(self) -> None:
        acc = KGAccumulator()
        acc.add_edge(
            self._edge("DR:A", "TREATS", "D:X", approval_year=1998, source="drugcentral"),
            priority=10,
        )
        acc.add_edge(
            self._edge("DR:A", "TREATS", "D:X", approval_year=None, source="primekg"),
            priority=5,
        )
        out = acc.to_output()
        assert out["edges"][0]["approval_year"] == 1998

    def test_priority_tag_stripped_from_output(self) -> None:
        acc = KGAccumulator()
        acc.add_edge(self._edge("DR:A", "TREATS", "D:X"), priority=5)
        out = acc.to_output()
        assert "_priority" not in out["edges"][0]

    def test_edge_without_required_fields_rejected(self) -> None:
        acc = KGAccumulator()
        added = acc.add_edge({"head": "DR:A", "rel": "TREATS"})  # no tail
        assert added is False
        assert acc.n_edges == 0

    def test_edges_distinguishable_by_relation(self) -> None:
        """Same (head, tail) but different rel → two distinct edges."""
        acc = KGAccumulator()
        acc.add_edge(self._edge("DR:A", "TREATS", "D:X"))
        acc.add_edge(self._edge("DR:A", "CONTRAINDICATED_FOR", "D:X"))
        assert acc.n_edges == 2

    def test_add_edges_batch(self) -> None:
        acc = KGAccumulator()
        edges = [self._edge(f"DR:{i}", "TREATS", "D:X") for i in range(4)]
        added = acc.add_edges(edges)
        assert added == 4
        assert acc.n_edges == 4


# ---------------------------------------------------------------------------
# KGAccumulator.to_output
# ---------------------------------------------------------------------------


class TestKGAccumulatorOutput:
    def test_to_output_empty(self) -> None:
        out = KGAccumulator().to_output()
        assert out["nodes"] == []
        assert out["edges"] == []

    def test_to_output_combined(self) -> None:
        acc = KGAccumulator()
        acc.add_node({"id": "D:A", "name": "A", "type": "Disease"})
        acc.add_node({"id": "DR:B", "name": "B", "type": "Drug"})
        acc.add_edge({"head": "DR:B", "rel": "TREATS", "tail": "D:A"})
        out = acc.to_output()
        assert len(out["nodes"]) == 2
        assert len(out["edges"]) == 1

    def test_to_output_is_stable(self) -> None:
        """Calling to_output() twice returns equal results."""
        acc = KGAccumulator()
        acc.add_node({"id": "D:A", "name": "A", "type": "Disease"})
        acc.add_edge({"head": "DR:B", "rel": "TREATS", "tail": "D:A"})
        assert acc.to_output() == acc.to_output()

"""Unit tests for pure-logic helper functions in the Phase-1 ingestors.

No disk I/O, no external files.  Tests exercise only the small utility
functions exported (or testable in isolation) from each ingestor module:

- app/etl/ingest/drugcentral.py  : _extract_year, _drug_cid, _disease_cid
- app/etl/ingest/hpo.py          : _hpo_canonical_id, _disease_cid_from_hpoa,
                                   _parse_hpo_obo (tiny OBO fixture)
- app/etl/ingest/reactome.py     : _pathway_cid
"""

from __future__ import annotations

import textwrap

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# DrugCentral helpers
# ---------------------------------------------------------------------------


class TestDrugCentralExtractYear:
    """app.etl.ingest.drugcentral._extract_year"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from app.etl.ingest.drugcentral import _extract_year

        self.fn = _extract_year

    def test_four_digit_year(self) -> None:
        assert self.fn("1998") == 1998

    def test_year_in_date_string(self) -> None:
        assert self.fn("1998-06-15") == 1998

    def test_year_in_parentheses(self) -> None:
        assert self.fn("approved (2005)") == 2005

    def test_20xx_year(self) -> None:
        assert self.fn("2019") == 2019

    def test_empty_string_returns_none(self) -> None:
        assert self.fn("") is None

    def test_no_year_returns_none(self) -> None:
        assert self.fn("not a year") is None

    def test_pre_1900_not_matched(self) -> None:
        # Our regex requires (19|20)XX
        assert self.fn("1855") is None

    def test_future_year_matched(self) -> None:
        # 2099 is technically valid (rare new approvals)
        assert self.fn("2099") == 2099


class TestDrugCentralDrugCid:
    """app.etl.ingest.drugcentral._drug_cid"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from app.etl.ingest.drugcentral import _drug_cid

        self.fn = _drug_cid

    def test_simple_name(self) -> None:
        cid = self.fn("Miglustat")
        assert cid == "DR:DC_MIGLUSTAT"

    def test_name_with_spaces(self) -> None:
        cid = self.fn("hydroxypropyl beta cyclodextrin")
        assert " " not in cid

    def test_name_with_hyphens(self) -> None:
        cid = self.fn("HP-beta-CD")
        assert cid.startswith("DR:DC_")
        # hyphens -> underscores; no double underscores
        assert "__" not in cid

    def test_fallback_to_struct_id_when_name_empty(self) -> None:
        cid = self.fn("", "42")
        assert "42" in cid

    def test_no_trailing_underscore(self) -> None:
        # A name with trailing punctuation should not produce a trailing underscore.
        # All-punctuation with a struct_id fallback is the safe call path in practice.
        cid = self.fn("drug!!!", "42")
        assert not cid.endswith("_")


class TestDrugCentralDiseaseCid:
    """app.etl.ingest.drugcentral._disease_cid"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from app.etl.ingest.drugcentral import _disease_cid

        self.fn = _disease_cid

    def test_omim_id_wins(self) -> None:
        cid = self.fn(omim_id="257220", do_id="DOID:893")
        assert cid == "D:OMIM_257220"

    def test_do_id_fallback(self) -> None:
        cid = self.fn(omim_id="", do_id="DOID:893")
        assert cid == "D:DOID_DOID_893"

    def test_no_ids_returns_none(self) -> None:
        assert self.fn(omim_id="", do_id="") is None

    def test_omim_leading_zeros_stripped(self) -> None:
        cid = self.fn(omim_id="000123")
        assert cid == "D:OMIM_123"

    def test_whitespace_omim_treated_as_missing(self) -> None:
        assert self.fn(omim_id="   ", do_id="") is None


# ---------------------------------------------------------------------------
# HPO helpers
# ---------------------------------------------------------------------------


class TestHpoCanonicalId:
    """app.etl.ingest.hpo._hpo_canonical_id"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from app.etl.ingest.hpo import _hpo_canonical_id

        self.fn = _hpo_canonical_id

    def test_standard_hpo_id(self) -> None:
        assert self.fn("HP:0001250") == "S:HP_0001250"

    def test_colon_replaced_with_underscore(self) -> None:
        cid = self.fn("HP:0001250")
        assert ":" not in cid.split(":", 1)[1]  # no colon after the prefix separator

    def test_prefix_is_S(self) -> None:
        assert self.fn("HP:0001250").startswith("S:")


class TestHpoDiseaseCidFromHpoa:
    """app.etl.ingest.hpo._disease_cid_from_hpoa"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from app.etl.ingest.hpo import _disease_cid_from_hpoa

        self.fn = _disease_cid_from_hpoa

    def test_omim_format(self) -> None:
        assert self.fn("OMIM:123456") == "D:OMIM_123456"

    def test_orpha_format(self) -> None:
        assert self.fn("ORPHA:586") == "D:ORPHA_586"

    def test_unknown_namespace_returns_none(self) -> None:
        assert self.fn("KEGG:H00001") is None

    def test_empty_returns_none(self) -> None:
        assert self.fn("") is None


class TestParseHpoObo:
    """app.etl.ingest.hpo._parse_hpo_obo — minimal OBO fixture.

    _parse_hpo_obo(path: Path) takes a file path and opens it internally,
    so tests must write content to a real tmp_path file.
    """

    _TINY_OBO = textwrap.dedent(
        """\
        format-version: 1.2
        data-version: releases/2024-04-26

        [Term]
        id: HP:0000001
        name: All
        comment: Root of HPO hierarchy.

        [Term]
        id: HP:0001250
        name: Seizure
        synonym: "Epileptic seizure" EXACT []
        is_a: HP:0000001 ! All

        [Term]
        id: HP:0099999
        name: Obsolete term
        is_obsolete: true
        """
    )

    @pytest.fixture()
    def obo_file(self, tmp_path):
        """Write the tiny OBO fixture to a temp file and return its Path."""
        p = tmp_path / "hp.obo"
        p.write_text(self._TINY_OBO, encoding="utf-8")
        return p

    @pytest.fixture()
    def empty_obo_file(self, tmp_path):
        p = tmp_path / "empty.obo"
        p.write_text("format-version: 1.2\n", encoding="utf-8")
        return p

    def test_parses_non_obsolete_terms(self, obo_file) -> None:
        from app.etl.ingest.hpo import _parse_hpo_obo

        terms = _parse_hpo_obo(obo_file)
        ids = [t["id"] for t in terms]
        assert "HP:0001250" in ids
        assert "HP:0000001" in ids

    def test_obsolete_terms_flagged_not_dropped(self, obo_file) -> None:
        """_parse_hpo_obo returns ALL terms; obsolete ones carry is_obsolete=True.
        Filtering is the caller's responsibility (see HPOIngestor.run())."""
        from app.etl.ingest.hpo import _parse_hpo_obo

        terms = {t["id"]: t for t in _parse_hpo_obo(obo_file)}
        assert "HP:0099999" in terms, "Obsolete term must be present in output"
        assert terms["HP:0099999"]["is_obsolete"] is True

    def test_term_has_name(self, obo_file) -> None:
        from app.etl.ingest.hpo import _parse_hpo_obo

        terms = {t["id"]: t for t in _parse_hpo_obo(obo_file)}
        assert terms["HP:0001250"]["name"] == "Seizure"

    def test_term_captures_synonym(self, obo_file) -> None:
        from app.etl.ingest.hpo import _parse_hpo_obo

        terms = {t["id"]: t for t in _parse_hpo_obo(obo_file)}
        assert "Epileptic seizure" in terms["HP:0001250"].get("synonyms", [])

    def test_term_captures_parent(self, obo_file) -> None:
        from app.etl.ingest.hpo import _parse_hpo_obo

        terms = {t["id"]: t for t in _parse_hpo_obo(obo_file)}
        assert "HP:0000001" in terms["HP:0001250"].get("is_a", [])

    def test_empty_file_returns_empty_list(self, empty_obo_file) -> None:
        from app.etl.ingest.hpo import _parse_hpo_obo

        assert _parse_hpo_obo(empty_obo_file) == []


# ---------------------------------------------------------------------------
# Reactome helpers
# ---------------------------------------------------------------------------


class TestReactomePathwayCid:
    """app.etl.ingest.reactome._pathway_cid"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from app.etl.ingest.reactome import _pathway_cid

        self.fn = _pathway_cid

    def test_standard_reactome_id(self) -> None:
        cid = self.fn("R-HSA-109581")
        assert cid == "PW:R_HSA_109581"

    def test_prefix_is_pw(self) -> None:
        assert self.fn("R-HSA-1234").startswith("PW:")

    def test_hyphens_replaced_with_underscores(self) -> None:
        cid = self.fn("R-HSA-123")
        assert "-" not in cid.split(":", 1)[1]

    def test_different_species_still_works(self) -> None:
        # Non-HSA species (should not appear in practice but the function is agnostic)
        cid = self.fn("R-MMU-109581")
        assert cid.startswith("PW:")
        assert "MMU" in cid

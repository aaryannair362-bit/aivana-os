"""
Tests for backend/app/lab_test_matcher.py -- the fuzzy lab-test-name corrector, added
alongside drug_matcher.py to fix the same class of AI-extraction-introduced misspellings for
recommended lab tests. Runs against the REAL dataset (backend/app/data/lab_tests.csv, 195
tests derived from the "IPD Lab Master Starter" reference) rather than a mocked fixture, for
the same reason test_drug_matcher.py does: the point is pinning down real behavior against the
real data.
"""
import copy

import pytest

from app import lab_test_matcher


def test_dataset_loads_and_has_the_expected_number_of_entries():
    names, exact_lookup, fuzzy_candidates = lab_test_matcher._load()
    assert len(names) == 195
    assert len(exact_lookup) > 195  # every test name AND every common alias is a key
    assert len(fuzzy_candidates) > 0


@pytest.mark.parametrize("exact_test_name", [
    "Complete Blood Count", "Widal Test", "Erythrocyte Sedimentation Rate", "TSH",
])
def test_exact_canonical_test_names_resolve_to_themselves(exact_test_name):
    assert lab_test_matcher.closest_lab_test_name(exact_test_name) == exact_test_name


@pytest.mark.parametrize("alias,expected_canonical", [
    ("CBC", "Complete Blood Count"),
    ("Widal", "Widal Test"),
    ("ESR", "Erythrocyte Sedimentation Rate"),
    ("LFT", "Liver Function Test"),
    ("RFT", "Renal Function Test"),
    ("Hb", "Hemoglobin"),
    ("HbA1c", "Glycated Hemoglobin"),
    ("CRP", "C-Reactive Protein"),
    ("WBC", "Total Leucocyte Count"),
    ("PSA", "Prostate Specific Antigen"),
])
def test_common_aliases_resolve_to_the_canonical_test_name(alias, expected_canonical):
    assert lab_test_matcher.closest_lab_test_name(alias) == expected_canonical


def test_alias_matching_is_case_and_whitespace_insensitive():
    assert lab_test_matcher.closest_lab_test_name("cbc") == "Complete Blood Count"
    assert lab_test_matcher.closest_lab_test_name("  CBC  ") == "Complete Blood Count"
    assert lab_test_matcher.closest_lab_test_name("complete blood count") == "Complete Blood Count"


@pytest.mark.parametrize("misspelled,expected_canonical", [
    ("Compleet Blood Count", "Complete Blood Count"),
    ("Dengu NS1", "Dengue NS1 Antigen"),
    ("Widal Tets", "Widal Test"),
])
def test_real_typos_are_corrected(misspelled, expected_canonical):
    assert lab_test_matcher.closest_lab_test_name(misspelled) == expected_canonical


@pytest.mark.parametrize("phrasing,expected_canonical", [
    ("Serum creatinine", "Serum Creatinine"),               # case only
    ("Liver function tests", "Liver Function Test"),        # case + plural
    ("Renal function tests", "Renal Function Test"),
    ("RA factor", "Rheumatoid Factor"),
    ("Dengue NS1 antigen", "Dengue NS1 Antigen"),
])
def test_casing_and_pluralization_variants_are_normalized(phrasing, expected_canonical):
    assert lab_test_matcher.closest_lab_test_name(phrasing) == expected_canonical


def test_completely_unrelated_input_returns_none():
    assert lab_test_matcher.closest_lab_test_name("random unrelated gibberish xyz123") is None


def test_empty_or_garbage_input_returns_none_without_raising():
    assert lab_test_matcher.closest_lab_test_name("") is None
    assert lab_test_matcher.closest_lab_test_name(None) is None
    assert lab_test_matcher.closest_lab_test_name("   ") is None


class TestShortCandidateFalsePositiveRegression:
    """
    Regression tests for a real bug caught during development: `fuzz.WRatio` includes
    partial_ratio, which rewards a SHORT candidate for appearing as a near-perfect substring
    alignment inside a much longer query, regardless of actual relevance -- "HBV DNA" matched
    the alias "Hb" (score 90) purely from character overlap, and "Fasting Blood Sugar" matched
    "AST" (Antibiotic Sensitivity Testing, score 90) because the letters "ast" literally occur
    inside the word "fASTing". Fixed by excluding candidates shorter than
    MIN_FUZZY_CANDIDATE_LENGTH from the fuzzy fallback pool (exact-match lookups, where these
    short aliases are handled correctly and unambiguously, are unaffected).
    """

    def test_hbv_dna_does_not_resolve_to_hemoglobin(self):
        result = lab_test_matcher.closest_lab_test_name("HBV DNA")
        assert result == "HBV DNA Quantitative"
        assert result != "Hemoglobin"

    def test_fasting_blood_sugar_is_not_forced_into_an_unrelated_test(self):
        # "Fasting Blood Glucose" (alias "FBS") only scores ~77 against "Fasting Blood Sugar"
        # -- a genuine synonym gap ("sugar" vs "glucose"), not a bug -- so this correctly stays
        # None rather than being forced into a wrong match like "Antibiotic Sensitivity Testing".
        assert lab_test_matcher.closest_lab_test_name("Fasting Blood Sugar") is None
        # The exact alias itself must still resolve correctly.
        assert lab_test_matcher.closest_lab_test_name("FBS") == "Fasting Blood Glucose"


class TestCorrectLabTestNames:
    def test_corrects_each_name_in_a_list(self):
        result = lab_test_matcher.correct_lab_test_names(["CBC", "Dengu NS1", "unrelatedxyz", "Widal"])
        assert result == ["Complete Blood Count", "Dengue NS1 Antigen", "unrelatedxyz", "Widal Test"]

    def test_preserves_order_and_count(self):
        names = ["CBC", "ESR", "LFT"]
        result = lab_test_matcher.correct_lab_test_names(names)
        assert len(result) == len(names)

    def test_non_list_input_is_returned_unchanged(self):
        assert lab_test_matcher.correct_lab_test_names(None) is None
        assert lab_test_matcher.correct_lab_test_names("not a list") == "not a list"

    def test_empty_list_is_a_no_op(self):
        assert lab_test_matcher.correct_lab_test_names([]) == []

    def test_tolerates_non_string_entries(self):
        result = lab_test_matcher.correct_lab_test_names(["CBC", None, "", 123])
        assert result[0] == "Complete Blood Count"
        assert result[1] is None
        assert result[3] == 123


class TestCorrectLabTestEntries:
    def test_corrects_the_test_key_and_records_the_original(self):
        entries = [{"test": "WBC", "result": "8000"}]
        result = lab_test_matcher.correct_lab_test_entries(entries, key="test")
        assert result[0]["test"] == "Total Leucocyte Count"
        assert result[0]["original_test"] == "WBC"
        assert result[0]["result"] == "8000"  # other fields untouched

    def test_leaves_unmatchable_entries_alone(self):
        entries = [{"test": "unrelatedxyz", "result": "1"}]
        result = lab_test_matcher.correct_lab_test_entries(entries, key="test")
        assert result[0]["test"] == "unrelatedxyz"
        assert "original_test" not in result[0]

    def test_tolerates_malformed_entries_without_raising(self):
        entries = [{"result": "no test key"}, {"test": ""}, {"test": None}, "not a dict", {"test": "CBC"}]
        result = lab_test_matcher.correct_lab_test_entries(entries, key="test")
        assert result[4]["test"] == "Complete Blood Count"

    def test_non_list_input_is_returned_unchanged(self):
        assert lab_test_matcher.correct_lab_test_entries(None) is None

    def test_does_not_mutate_a_separately_held_reference_incorrectly(self):
        # Sanity check that deepcopy is the right pattern for callers comparing before/after.
        original = [{"test": "WBC", "result": "8000"}]
        snapshot = copy.deepcopy(original)
        lab_test_matcher.correct_lab_test_entries(original, key="test")
        assert original != snapshot  # the live object WAS mutated (documented behavior)
        assert snapshot == [{"test": "WBC", "result": "8000"}]  # the deep copy was not


class TestScribeIntegration:
    """Confirms scribe.scribe_transcript and main.nurse_consult actually apply the correction
    to their real output, not just that lab_test_matcher works in isolation."""

    def test_scribe_transcript_corrects_lab_test_names(self, monkeypatch):
        from app.scribe import scribe
        import json as _json

        monkeypatch.setattr(scribe, "_call_groq_api", lambda *a, **k: _json.dumps({
            "chiefComplaint": "fever", "labTests": ["CBC", "Widal"],
        }))
        result = scribe.scribe_transcript("doctor patient transcript long enough to pass validation")
        assert result["labTests"] == ["Complete Blood Count", "Widal Test"]

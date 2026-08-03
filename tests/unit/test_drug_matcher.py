"""
Tests for backend/app/drug_matcher.py -- the fuzzy medicine-name corrector added to fix
AI-extraction-introduced brand-name misspellings (see that module's docstring, and
_find_correction's, for the full rationale including two real bug classes found and fixed
during development: form/route swaps, and look-alike-sound-alike brand collisions on bare
generic names). Runs against the REAL dataset (backend/app/data/medicine_names.csv, ~249k
names) rather than a mocked/tiny fixture, since the whole point of these cases is pinning down
real behavior against the real data -- a fake tiny dataset would validate the algorithm but not
the actual threshold/quality tradeoff made here.

Every positive (should-correct) case below states an explicit form word ("Tablet X"), matching
this app's own OPD prescribing convention (see tests/from_data/fixtures.py) -- drug_matcher
only ever acts when a form is stated; see test_bare_generic_names_are_never_touched for why.
"""
import pytest

from app import drug_matcher


def test_dataset_loads_and_has_a_realistic_number_of_entries():
    full_names, bases, forms = drug_matcher._load()
    assert len(full_names) > 200_000
    assert len(full_names) == len(bases) == len(forms)


@pytest.mark.parametrize("misspelled,expected_substring", [
    ("Tablet Zanocine", "Zanocin"),
    ("Tablet Calpoll", "Calpol"),
    ("Tablet Paracetmol 500mg", "Paracetamol"),
])
def test_real_typos_are_corrected_to_the_right_brand(misspelled, expected_substring):
    result = drug_matcher.closest_medicine_name(misspelled)
    assert result is not None, f"expected a confident correction for {misspelled!r}, got None"
    assert expected_substring.lower() in result.lower()


@pytest.mark.parametrize("form_stated_name", ["Tablet Zanocin", "Tablet Calpol"])
def test_known_brand_names_from_the_reference_prescriptions_resolve_to_a_real_product(form_stated_name):
    result = drug_matcher.closest_medicine_name(form_stated_name)
    assert result is not None
    # the corrected name must still carry the same brand token, not drift to an unrelated product
    base_token = form_stated_name.replace("Tablet", "").strip().split()[0].lower()
    assert base_token in result.lower()


@pytest.mark.parametrize("bare_name", [
    "Zanocin", "Calpol", "Augmentin", "Crocin", "Metrogyl",  # already correctly spelled brands
    "Diclofenac", "Aspirin", "Metformin", "Chloroquine",     # already correctly spelled generics
])
def test_bare_generic_names_are_never_touched(bare_name):
    """
    Core design decision, not an incidental gap: a drugName with NO stated pharmaceutical
    form/route is never corrected, even when it's already spelled perfectly (Zanocin, Aspirin)
    or misspelled (see test_real_typos_are_corrected_to_the_right_brand, which uses the SAME
    brand names but with a form word present and gets a real correction). Bare-name correction
    was tried and reverted during development: "Aspirin"/"Diclofenac"/"Metformin"/"Chloroquine"
    (all correctly spelled, real generic names) were being silently rewritten into a specific
    branded dose+form product -- in Diclofenac's and Chloroquine's cases, into a DIFFERENT real
    look-alike-sound-alike brand ("Dicofenac", "Chloroquin") scoring in the exact same range as
    genuine typo fixes, which is not solvable by threshold tuning (see _find_correction).
    """
    assert drug_matcher.closest_medicine_name(bare_name) is None


def test_a_real_drug_missing_from_the_dataset_is_left_unchanged_rather_than_force_matched():
    # "Electral" (a very common Indian ORS brand) does not appear anywhere in the source
    # dataset (verified directly against the CSV) -- the nearest entries are a different,
    # unrelated product family. Forcing a substitution here would be a clinically wrong
    # correction, not a fix, so this must return None rather than the closest-but-wrong entry.
    assert drug_matcher.closest_medicine_name("Electral Powder") is None


def test_empty_or_garbage_input_returns_none_without_raising():
    assert drug_matcher.closest_medicine_name("") is None
    assert drug_matcher.closest_medicine_name(None) is None
    assert drug_matcher.closest_medicine_name("   ") is None
    assert drug_matcher.closest_medicine_name("x") is None  # below MIN_BASE_LENGTH after stripping


@pytest.mark.parametrize("stated_form_drug", [
    "Antacid Syrup", "Diclofenac Gel", "Antacid Suspension", "Salbutamol Inhaler",
])
def test_stated_form_is_never_silently_changed_to_a_different_form(stated_form_drug):
    """
    Regression test for a real, patient-safety-relevant bug caught during development: brand-
    name-only similarity, with no form awareness, matched each of these (a correctly-spelled
    generic name, or a generic category term) to a WRONG, differently-formed product purely on
    character closeness -- "Diclofenac Gel" (topical) to "Dicofenac Injection" (injectable),
    "Antacid Syrup"/"Antacid Suspension" to "Antacid ... Tablet", "Salbutamol Inhaler" to a
    tablet product. A form/route swap is never a legitimate "spelling correction" -- the
    correct behavior is no match at all (this asserts None), not a differently-formed one.
    """
    assert drug_matcher.closest_medicine_name(stated_form_drug) is None


def test_a_stated_form_restricts_candidates_to_that_same_form():
    """
    Positive-side check for the same constraint: "Tablet Zanocin" must never resolve to
    "Zanocin 100 Liquid" (a real dataset entry, and previously a possible outcome before the
    disambiguation/form-constraint fixes) -- only tablet variants are eligible at all.
    """
    result = drug_matcher.closest_medicine_name("Tablet Zanocin")
    assert result is not None
    assert "tablet" in result.lower()
    assert "liquid" not in result.lower()


def test_look_alike_sound_alike_collision_is_eliminated_for_bare_names_by_the_form_requirement():
    """
    "Azithromycin 500" has no stated form/route, so it's never even considered for correction
    -- eliminating (not just documenting) the look-alike-sound-alike collision with the real,
    different brand "Zithromycin" that a form-free version of this matcher exhibited during
    development (same root cause as test_bare_generic_names_are_never_touched). The general
    problem class -- a differently-spelled real brand sharing the same stated form -- isn't
    proven impossible, just meaningfully narrowed; not chased further here (see
    _find_correction's docstring).
    """
    assert drug_matcher.closest_medicine_name("Azithromycin 500") is None


def test_threshold_is_respected():
    # A very low threshold should find *some* tablet-form match for almost any garbled input.
    assert drug_matcher.closest_medicine_name("Tablet Zzzznocinnn", threshold=1) is not None
    # A threshold of exactly 100 should only match something that reduces to an identical base.
    assert drug_matcher.closest_medicine_name("Tablet Zanocin", threshold=100) is not None
    assert drug_matcher.closest_medicine_name("Tablet Zanocine", threshold=100) is None  # not identical


class TestCorrectMedicationNames:
    def test_corrects_in_place_and_records_the_original(self):
        meds = [{"drugName": "Tablet Zanocine", "dose": "200 mg", "frequency": "BID", "route": "Oral", "duration": "5 days"}]
        result = drug_matcher.correct_medication_names(meds)
        assert result[0]["drugName"] != "Tablet Zanocine"
        assert "Zanocin" in result[0]["drugName"]
        assert result[0]["original_drug_name"] == "Tablet Zanocine"
        # non-name fields must survive untouched
        assert result[0]["dose"] == "200 mg"
        assert result[0]["frequency"] == "BID"

    def test_leaves_unmatchable_or_missing_drugs_alone(self):
        meds = [{"drugName": "Electral Powder", "dose": "1 sachet"}]
        result = drug_matcher.correct_medication_names(meds)
        assert result[0]["drugName"] == "Electral Powder"
        assert "original_drug_name" not in result[0]

    def test_bare_names_are_left_alone_even_inside_a_medications_list(self):
        meds = [{"drugName": "Aspirin", "dose": "325mg", "route": "Oral"}]
        result = drug_matcher.correct_medication_names(meds)
        assert result[0]["drugName"] == "Aspirin"
        assert "original_drug_name" not in result[0]

    def test_tolerates_malformed_entries_without_raising(self):
        meds = [
            {"dose": "no drugName key at all"},
            {"drugName": ""},
            {"drugName": None},
            "not even a dict",
            {"drugName": "Tablet Calpoll"},
        ]
        result = drug_matcher.correct_medication_names(meds)
        assert result[4]["drugName"] != "Tablet Calpoll"

    def test_non_list_input_is_returned_unchanged(self):
        assert drug_matcher.correct_medication_names(None) is None
        assert drug_matcher.correct_medication_names("not a list") == "not a list"

    def test_empty_list_is_a_no_op(self):
        assert drug_matcher.correct_medication_names([]) == []

    def test_dose_disambiguates_same_brand_ties_to_the_right_strength_and_form(self):
        """
        Regression test for a real bug caught during development: "Zanocin"/"Calpol" have
        several dataset entries (different strengths -- 200mg vs 100mg) that all reduce to the
        identical stripped base and tie on score. Without using the medication's own dose to
        break the tie, the first tied entry in dataset order won arbitrarily -- e.g. "Tablet
        Zanocin" at 200mg once resolved to a 100mg variant, contradicting the medication's own
        dose field.
        """
        meds = [
            {"drugName": "Tablet Zanocin", "dose": "200 mg", "route": "Oral"},
            {"drugName": "Tablet Calpol", "dose": "500 mg", "route": "Oral"},
        ]
        result = drug_matcher.correct_medication_names(meds)
        assert result[0]["drugName"] == "Zanocin 200 Tablet"
        assert result[1]["drugName"] == "Calpol 500mg Tablet"

    def test_dose_number_matching_is_digit_adjacent_not_word_boundary(self):
        """
        Regression test for the specific bug behind the fix above: `\\b500\\b` never matches
        inside "Calpol 500mg Tablet" because "500" and "mg" are both regex word characters
        with no boundary between them -- verified live, this silently picked "Calpol 1000mg
        Tablet" instead before the digit-adjacency fix.
        """
        meds = [{"drugName": "Tablet Calpol", "dose": "500 mg"}]
        assert drug_matcher.correct_medication_names(meds)[0]["drugName"] == "Calpol 500mg Tablet"


class TestScribeIntegration:
    """Confirms scribe.scribe_transcript and generate_discharge_summary actually apply the
    correction to their real output, not just that drug_matcher works in isolation."""

    def test_scribe_transcript_corrects_medication_names(self, monkeypatch):
        from app.scribe import scribe
        import json as _json

        monkeypatch.setattr(scribe, "_call_groq_api", lambda *a, **k: _json.dumps({
            "chiefComplaint": "fever", "medications": [
                {"drugName": "Tablet Zanocine", "dose": "200 mg", "frequency": "BID", "route": "Oral", "duration": "5 days"},
            ],
        }))
        result = scribe.scribe_transcript("doctor patient transcript long enough to pass validation")
        assert result["medications"][0]["drugName"] != "Tablet Zanocine"
        assert "Zanocin" in result["medications"][0]["drugName"]

    def test_discharge_summary_corrects_medications_at_discharge(self, monkeypatch):
        from app.scribe import scribe
        import json as _json

        monkeypatch.setattr(scribe, "_call_groq_api", lambda *a, **k: _json.dumps({
            "admissionSummary": "x", "medicationsAtDischarge": [
                {"drugName": "Tablet Calpoll", "dose": "500 mg", "frequency": "SOS", "duration": "5 days"},
            ],
        }))
        result = scribe.generate_discharge_summary({"patient_name": "Test"})
        assert result["medicationsAtDischarge"][0]["drugName"] != "Tablet Calpoll"
        assert "Calpol" in result["medicationsAtDischarge"][0]["drugName"]

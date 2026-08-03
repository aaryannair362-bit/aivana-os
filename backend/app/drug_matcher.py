"""
Fuzzy-corrects AI-extracted medication names against a canonical Indian medicines database
(backend/app/data/medicine_names.csv -- ~249k unique brand/generic product names, derived from
a user-supplied "A-Z medicines dataset of India" export; only the `name` column is kept, since
that's all this feature uses).

Why this exists: the voice -> LLM extraction pipeline (scribe.scribe_transcript) misspells
brand names a meaningful fraction of the time (e.g. "Zanocine" for "Zanocin", "Calpoll" for
"Calpol") -- ASR/LLM noise, not a data-entry error a doctor would catch by eye on a short
drug name they already trust. This module looks up the closest real product name and swaps it
in before the prescription is ever shown to the doctor, the same way a pharmacy system's
autocomplete would.

Only ever acts on a drugName that states an explicit form/route ("Tablet Zanocin", "Tab
Aceclofenac" -- the convention this app's own OPD pipeline actually uses; see
tests/from_data/fixtures.py), and never crosses to a different form than the one stated. A bare
generic/brand name with no form ("Diclofenac", "Aspirin") is left untouched, even when it's
misspelled. See _find_correction's docstring for the two real bug classes (dangerous form/route
swaps, and look-alike-sound-alike brand collisions on bare names) this conservatism exists to
avoid -- both found live, against real pre-existing test fixtures, during development.

Matching strategy: dataset names embed strength/form in the string itself
("Zanocin 200 Tablet", "Calpol 500mg Tablet"), which would dominate a naive full-string fuzzy
score far more than the brand name itself does (verified empirically -- see the two rejected
approaches below). So both the query and every candidate are reduced to a "base" (brand-name-
only, dose/form words stripped) before scoring, and the ORIGINAL full canonical name is what
gets substituted back in -- never the stripped base -- so the output still carries a real
strength/form, not a bare brand name.

Two approaches were tried and rejected before this one (see the conversation this shipped in
for the actual benchmark numbers, not repeated here):
  1. `rapidfuzz.fuzz.WRatio` / `token_set_ratio` against the full (unstripped) name strings --
     ~250-400ms per query against all ~249k candidates (too slow to run per-drug on every
     prescription), and prone to high-confidence WRONG matches: "Electral Powder" scored 85.5
     against "Abitate 250mg Powder for Injection" purely because both strings share "Powder"
     and similar overall length -- nothing to do with the actual drug.
  2. Stripped bases with `fuzz.WRatio` -- still slow (WRatio computes several sub-metrics per
     comparison) for no accuracy gain over plain `fuzz.ratio` once the dose/form noise is
     already removed.
The shipped approach (stripped bases + `fuzz.ratio`) benchmarked at ~15ms per query and did not
reproduce that false-positive class in the same test set.
"""
import re
import threading
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process

DATA_PATH = Path(__file__).resolve().parent / "data" / "medicine_names.csv"
CUSTOM_DATA_PATH = Path(__file__).resolve().parent / "data" / "custom_medicines.csv"

# Below this score (0-100, rapidfuzz's `fuzz.ratio` scale, computed on the stripped "base" --
# see module docstring), among same-form candidates (see _find_correction), the closest dataset
# entry is judged more likely to be a different real product sharing that form than a
# misspelling of the query, so the original extracted name is left untouched. Chosen
# empirically against a mixed test set of real typos with a form stated (Tablet Zanocine/Tablet
# Calpoll/Tablet Paracetmol, all scored 92-95 and were correctly fixed) versus a missing-from-
# dataset query (Electral Powder, scored 87.5 against a wrong product and must NOT be
# "corrected" into one) -- 92 sits in the gap. Not a universal constant; a different/larger
# dataset would need this re-validated the same way.
DEFAULT_MATCH_THRESHOLD = 92.0

# A stripped base shorter than this is almost certainly a stray fragment (dataset entries that
# are mostly/entirely dose+form words) rather than a real brand name, and short strings produce
# unreliably high `fuzz.ratio` scores against other short strings by chance alone -- excluded
# from the candidate pool entirely rather than risking a confident match to a fragment.
MIN_BASE_LENGTH = 2

_FORM_WORDS = (
    r"tablets?|capsules?|syrups?|injections?|creams?|ointments?|powders?|gels?|drops?|"
    r"suspensions?|solutions?|liquids?|sprays?|inhalers?|sachets?|patches?|soaps?|shampoos?|"
    r"lozenges?|granules?|kits?|strips?|suppositor(?:y|ies)|chewable|effervescent|paediatric|"
    r"redi|mouthwash|toothpaste|lotions?|elixir|gargle|infant|infants|oral|nasal|eye|ear|topical"
)
# Deliberately NOT stripped, unlike the packaging words above: "Plus"/"Forte" mark a genuinely
# different combination formulation in Indian pharma brand naming (e.g. "Calpol" plain
# paracetamol vs "Calpol Plus" a different active-ingredient combination), and "ER/SR/CR/XR/
# DT/OD/LA"-type suffixes mark a real release-mechanism difference (extended- vs immediate-
# release) with actual dosing/safety consequences -- collapsing either into the same "base" as
# the plain product caused exactly this kind of wrong match during testing (a misspelled
# "Calpoll" was "corrected" into "Calpol Plus", a different formulation) and was removed for
# that reason, not stripped by omission.
_DOSE_RE = re.compile(r"\d+(\.\d+)?\s*(mg|gm|g|ml|mcg|iu|%|w/w|w/v|/ml|/5ml)?", re.IGNORECASE)
_FORM_RE = re.compile(rf"\b(?:{_FORM_WORDS})\b", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^\w\s-]")
_WS_RE = re.compile(r"\s+")


def _strip_to_base(name: str) -> str:
    """Reduces a medicine name to just its brand/generic-name tokens: strips dose numbers+units
    and common form/pack words, drops punctuation, lowercases, collapses whitespace."""
    s = _DOSE_RE.sub(" ", name)
    s = _FORM_RE.sub(" ", s)
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip().lower()


_load_lock = threading.Lock()
_full_names: Optional[list] = None
_bases: Optional[list] = None
_forms: Optional[list] = None


def _read_names(path: Path) -> list:
    if not path.exists():
        return []
    import csv
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        return [(row.get("name") or "").strip() for row in csv.DictReader(f)]


def _load() -> tuple:
    """Lazily loads and indexes the dataset (primary + any admin-added custom entries) on
    first use, cached for the process lifetime. Never raises: a missing/unreadable dataset
    file just means every lookup finds nothing, same as the "no confident match" case --
    callers keep whatever name they already had. Precomputes each entry's form word
    (Tablet/Syrup/Gel/...), if any, alongside its stripped base -- see the hard form
    constraint in _find_correction for why this matters."""
    global _full_names, _bases, _forms
    if _full_names is not None:
        return _full_names, _bases, _forms
    with _load_lock:
        if _full_names is not None:  # another thread may have finished loading while we waited
            return _full_names, _bases, _forms
        _rebuild()
    return _full_names, _bases, _forms


def _rebuild() -> None:
    """(Re)builds the in-memory index from disk. Called on first use, and again by
    invalidate_cache() after an admin adds a custom medicine, so the new entry is matchable
    immediately without restarting the server."""
    global _full_names, _bases, _forms
    full_names, bases, forms = [], [], []
    try:
        names = _read_names(DATA_PATH) + _read_names(CUSTOM_DATA_PATH)
    except OSError:
        names = []
    for name in names:
        if not name:
            continue
        base = _strip_to_base(name)
        if len(base) < MIN_BASE_LENGTH:
            continue
        form_match = _FORM_RE.search(name)
        full_names.append(name)
        bases.append(base)
        forms.append(form_match.group(0).lower() if form_match else None)
    _full_names, _bases, _forms = full_names, bases, forms


def invalidate_cache() -> None:
    """Forces the next lookup to reload from disk -- call after writing a new row to
    custom_medicines.csv so an admin-added medicine is usable in the same process without a
    restart."""
    global _full_names, _bases, _forms
    with _load_lock:
        _full_names = _bases = _forms = None


# How close two candidates' scores must be to count as "tied" for dose/form disambiguation
# purposes, rather than one simply being the clear winner. fuzz.ratio scores on the same base
# string are exactly equal for genuine ties (e.g. every "Zanocin ..." variant scores identically
# against query base "zanocin"), so this only exists as a defensive float-comparison margin.
_TIE_MARGIN = 0.5
_DOSE_NUMBER_RE = re.compile(r"\d+(\.\d+)?")


def _extract_dose_number(text) -> Optional[str]:
    if not text or not isinstance(text, str):
        return None
    m = _DOSE_NUMBER_RE.search(text)
    return m.group(0) if m else None


def _disambiguate_tied_candidates(tied: list, full_names: list, drug_name: str, dose) -> str:
    """
    Among dataset entries that tied on base-name similarity (and, if the query stated a form,
    already all share that form -- see _find_correction), prefers whichever one's full name
    actually contains the same dose number the medication was recorded with -- so "Tablet
    Zanocin" prescribed at "200 mg" resolves to "Zanocin 200 Tablet", not an arbitrary
    same-brand different-strength tablet variant that would silently contradict the
    medication's own dose field. Falls back to the first tied entry (dataset order) if the dose
    doesn't narrow it down either.
    """
    dose_number = _extract_dose_number(dose)

    def _preference_score(candidate) -> int:
        _, _, index = candidate
        name_lower = full_names[index].lower()
        # Not a `\b...\b` word-boundary match: "500" and "mg" in "500mg" are both `\w`
        # characters with no boundary between them, so `\b500\b` would never match inside a
        # dataset name like "Calpol 500mg Tablet" -- checked live, this silently picked the
        # wrong strength (1000mg) before being caught. Match on digit-adjacency instead: not
        # preceded/followed by another digit, so "500" matches in "500mg" but not in "1500mg".
        if dose_number and re.search(rf"(?<!\d){re.escape(dose_number)}(?!\d)", name_lower):
            return 1
        return 0

    best = max(tied, key=_preference_score)
    _, _, index = best
    return full_names[index]


def _find_correction(drug_name: str, dose=None, threshold: float = DEFAULT_MATCH_THRESHOLD) -> Optional[str]:
    """
    Shared implementation behind both closest_medicine_name and correct_medication_names.

    Only attempts a correction at all when `drug_name` states an explicit pharmaceutical
    form/route word (Tablet/Syrup/Injection/Gel/Inhaler/...) -- and even then, only ever
    considers dataset entries stating that SAME form, never substituted with a different one no
    matter how high the brand-name similarity scores. A bare generic/brand name with no stated
    form (e.g. "Diclofenac", "Aspirin", "Metformin", "Azithromycin") is left untouched entirely.

    This is deliberately more conservative than "fix anything that scores high enough," and two
    real, distinct bug classes found live during development are why:
      1. Form/route swaps: brand-name-only similarity matched "Diclofenac Gel" (correctly
         spelled) to "Dicofenac Injection" (gel -> injection), "Antacid Syrup"/"Antacid
         Suspension" to "Antacid ... Tablet", "Salbutamol Inhaler" to a tablet product -- none
         of these are spelling corrections, they're silent, dangerous route changes.
      2. Look-alike-sound-alike (LASA) brand collisions on bare generic names: "Diclofenac"
         (correctly spelled) vs the real, different brand "Dicofenac" scores 94.7 on
         fuzz.ratio; "Azithromycin" vs the real, different brand "Zithromycin" scores 95.7;
         "Chloroquine" vs "Chloroquin" scores 95.2. These sit in the SAME score band as
         genuine, wanted typo fixes ("Zanocine"->"Zanocin" scores 93.3, "Calpoll"->"Calpol"
         scores 92.3) -- verified directly, there is no threshold that separates the two
         classes, because pure string similarity cannot distinguish "the query is misspelled"
         from "a different real product happens to be similarly spelled" (a well-known hard
         problem in pharmacy safety -- production systems solve it with curated LASA
         confusion lists, which is out of scope here). Requiring a stated form/route
         eliminates this whole risk category rather than trying to threshold around it: in
         practice, real prescriptions from this app's own OPD pipeline consistently state a
         form ("Tab X", "Tablet X" -- see tests/from_data/fixtures.py), so this still covers
         the dominant real-world case without gambling on bare generic names.
    """
    if not drug_name or not isinstance(drug_name, str):
        return None
    query_base = _strip_to_base(drug_name)
    if len(query_base) < MIN_BASE_LENGTH:
        return None

    form_match = _FORM_RE.search(drug_name)
    query_form = form_match.group(0).lower() if form_match else None
    if not query_form:
        return None

    full_names, bases, forms = _load()
    if not bases:
        return None

    eligible = [i for i, f in enumerate(forms) if f == query_form]
    if not eligible:
        return None
    subset_bases = [bases[i] for i in eligible]
    raw = process.extract(query_base, subset_bases, scorer=fuzz.ratio, score_cutoff=threshold, limit=50)
    matches = [(text, score, eligible[local_index]) for text, score, local_index in raw]

    if not matches:
        return None
    top_score = matches[0][1]
    tied = [m for m in matches if m[1] >= top_score - _TIE_MARGIN]
    if len(tied) == 1:
        return full_names[tied[0][2]]
    return _disambiguate_tied_candidates(tied, full_names, drug_name, dose)


def closest_medicine_name(query: str, threshold: float = DEFAULT_MATCH_THRESHOLD) -> Optional[str]:
    """
    Returns the closest canonical medicine name to `query` from the dataset (with its real
    strength/form intact), or None if nothing scores at/above `threshold` (including when
    `query` states a form and no same-form entry qualifies -- see _find_correction) --
    callers should keep the original name in that case rather than treat None as an error.
    """
    return _find_correction(query, dose=None, threshold=threshold)


def correct_medication_names(medications: list, threshold: float = DEFAULT_MATCH_THRESHOLD) -> list:
    """
    Applied to a prescription's `medications` list (each a dict with a "drugName" key) right
    after AI extraction, before the draft ever reaches the doctor: replaces each drugName with
    its closest canonical match from the medicines dataset, if one scores high enough --
    never crossing a stated pharmaceutical form/route (see _find_correction's hard constraint),
    and disambiguating same-brand/same-form ties using the medication's own dose (see
    _disambiguate_tied_candidates) rather than picking an arbitrary variant. Leaves
    dose/frequency/route/duration untouched, and leaves drugName alone (no key added) whenever
    no confident match is found -- including when the dataset itself is unavailable, so this
    can never turn a working prescription flow into a broken one.
    """
    if not isinstance(medications, list):
        return medications
    for med in medications:
        if not isinstance(med, dict):
            continue
        original = med.get("drugName")
        if not original or not isinstance(original, str):
            continue
        corrected = _find_correction(original, dose=med.get("dose"), threshold=threshold)
        if corrected and corrected != original:
            med["drugName"] = corrected
            med["original_drug_name"] = original
    return medications

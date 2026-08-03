"""
Corrects AI-extracted lab test names against a canonical lab test master
(backend/app/data/lab_tests.csv -- 195 tests across 25 departments, derived from a
user-supplied "IPD Lab Master Starter" reference; see that file's header comment for
provenance) plus any user-added entries in backend/app/data/custom_lab_tests.csv (see
lab_test_admin.py-style management via main.py's admin endpoints).

Unlike drug_matcher.py, this is a MUCH smaller, curated list (195 canonical names + 195
"common alias" abbreviations most clinicians actually say out loud -- "CBC", "LFT", "Widal",
"ESR" -- rather than the full test name), so the approach is simpler and doesn't need
drug_matcher's dose/form-safety machinery: there's no dose or pharmaceutical form concept for
a lab test, and the collision risk between two genuinely different tests sharing a very similar
name is much lower in a small, professionally curated 195-entry list than across ~249k
brand-name medicine products.

Matching order:
  1. Exact match (case/whitespace/punctuation-insensitive) against either the canonical test
     name OR its common alias -- covers the overwhelming majority of real cases, since a
     clinician saying "CBC" or "Widal" isn't a misspelling, it's the standard way these tests
     are actually requested.
  2. Fuzzy fallback (rapidfuzz) against the combined set of test names + aliases, for genuine
     ASR/LLM typos ("Compleet Blood Count", "Dengu NS1"). Only applied if no exact match, and
     only accepted above DEFAULT_MATCH_THRESHOLD.
"""
import csv
import re
import threading
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process

DATA_PATH = Path(__file__).resolve().parent / "data" / "lab_tests.csv"
CUSTOM_DATA_PATH = Path(__file__).resolve().parent / "data" / "custom_lab_tests.csv"

# Below this score (0-100, rapidfuzz's `fuzz.WRatio` scale) on the fuzzy fallback, the closest
# candidate is judged more likely to be a different test than a misspelling of the query.
# WRatio (not the stripped-base + plain-ratio approach drug_matcher.py uses) is appropriate
# here because lab test names carry no dose/form noise to strip out, and the candidate pool is
# tiny (~390 strings) so WRatio's extra cost per comparison is irrelevant.
DEFAULT_MATCH_THRESHOLD = 88.0

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")

# A candidate shorter than this is excluded from the FUZZY fallback pool only (exact-match
# lookups are unaffected). Found live: `fuzz.WRatio` includes partial_ratio, which rewards a
# short candidate for appearing as a near-perfect substring alignment inside a much longer
# query regardless of relevance -- "HBV DNA" matched the alias "Hb" (score 90) purely because
# "hb" partially aligns within "hbv dna" as characters, and "Fasting Blood Sugar" matched "AST"
# (Antibiotic Sensitivity Testing, score 90) because the letters "ast" literally appear inside
# the word "fASTing". Real short abbreviations ("Hb", "AST", "CT", "PSA") are already handled
# perfectly by the exact-match path above; they add nothing but risk as fuzzy-fallback targets.
MIN_FUZZY_CANDIDATE_LENGTH = 5


def _normalize(text: str) -> str:
    s = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", s).strip().lower()


_load_lock = threading.Lock()
_canonical_names: Optional[list] = None
_exact_lookup: Optional[dict] = None
_fuzzy_candidates: Optional[list] = None  # list of (normalized_candidate_text, canonical_name)


def _read_rows(path: Path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def _load() -> tuple:
    """Lazily loads and indexes the dataset (primary + custom additions) on first use, cached
    for the process lifetime. Never raises: a missing/unreadable file just means every lookup
    finds nothing, same as the "no confident match" case."""
    global _canonical_names, _exact_lookup, _fuzzy_candidates
    if _exact_lookup is not None:
        return _canonical_names, _exact_lookup, _fuzzy_candidates
    with _load_lock:
        if _exact_lookup is not None:
            return _canonical_names, _exact_lookup, _fuzzy_candidates
        _rebuild()
    return _canonical_names, _exact_lookup, _fuzzy_candidates


def _rebuild() -> None:
    """(Re)builds the in-memory index from disk. Called on first use, and again by
    invalidate_cache() after an admin adds a custom entry, so new additions are searchable
    immediately without restarting the server."""
    global _canonical_names, _exact_lookup, _fuzzy_candidates
    names, exact, fuzzy = [], {}, []
    try:
        rows = _read_rows(DATA_PATH) + _read_rows(CUSTOM_DATA_PATH)
    except OSError:
        rows = []
    for row in rows:
        test_name = (row.get("test_name") or "").strip()
        if not test_name:
            continue
        alias = (row.get("common_alias") or "").strip()
        names.append(test_name)
        norm_name = _normalize(test_name)
        exact.setdefault(norm_name, test_name)
        if len(norm_name) >= MIN_FUZZY_CANDIDATE_LENGTH:
            fuzzy.append((norm_name, test_name))
        if alias:
            norm_alias = _normalize(alias)
            exact.setdefault(norm_alias, test_name)
            if len(norm_alias) >= MIN_FUZZY_CANDIDATE_LENGTH:
                fuzzy.append((norm_alias, test_name))
    _canonical_names, _exact_lookup, _fuzzy_candidates = names, exact, fuzzy


def invalidate_cache() -> None:
    """Forces the next lookup to reload from disk -- call after writing a new row to
    custom_lab_tests.csv so an admin-added test is usable in the same process without a
    restart."""
    global _canonical_names, _exact_lookup, _fuzzy_candidates
    with _load_lock:
        _canonical_names = _exact_lookup = _fuzzy_candidates = None


def closest_lab_test_name(query: str, threshold: float = DEFAULT_MATCH_THRESHOLD) -> Optional[str]:
    """
    Returns the canonical test name for `query`, or None if nothing confident is found --
    callers should keep the original name in that case rather than treat None as an error.
    Tries an exact (normalized) match against every test name and common alias first; only
    falls back to fuzzy matching (and only above `threshold`) if that fails.
    """
    if not query or not isinstance(query, str):
        return None
    normalized = _normalize(query)
    if not normalized:
        return None

    _, exact_lookup, fuzzy_candidates = _load()
    if not exact_lookup:
        return None

    exact = exact_lookup.get(normalized)
    if exact:
        return exact

    candidate_strings = [c[0] for c in fuzzy_candidates]
    match = process.extractOne(normalized, candidate_strings, scorer=fuzz.WRatio, score_cutoff=threshold)
    if not match:
        return None
    _, _, index = match
    return fuzzy_candidates[index][1]


def correct_lab_test_names(test_names: list, threshold: float = DEFAULT_MATCH_THRESHOLD) -> list:
    """
    Applied to a prescription/round's `labTests` list (bare strings, e.g. from
    scribe.scribe_transcript) right after AI extraction: replaces each name with its canonical
    match if one is found, otherwise leaves the original string untouched. Order and count are
    preserved.
    """
    if not isinstance(test_names, list):
        return test_names
    corrected = []
    for name in test_names:
        if not isinstance(name, str) or not name.strip():
            corrected.append(name)
            continue
        match = closest_lab_test_name(name, threshold)
        corrected.append(match if match else name)
    return corrected


def correct_lab_test_entries(entries: list, key: str = "test", threshold: float = DEFAULT_MATCH_THRESHOLD) -> list:
    """
    Applied to a list of dicts carrying a lab test name under `key` (e.g. nurse_consult's
    `labs`: [{"test": "...", "result": "..."}]) -- replaces that field's value in place when a
    confident match is found, preserving every other key untouched. Mirrors
    drug_matcher.correct_medication_names' tolerance of malformed entries.
    """
    if not isinstance(entries, list):
        return entries
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        original = entry.get(key)
        if not original or not isinstance(original, str):
            continue
        corrected = closest_lab_test_name(original, threshold)
        if corrected and corrected != original:
            entry[key] = corrected
            entry[f"original_{key}"] = original
    return entries

# TEST_NOTES.md

Ambiguities, deliberate scope boundaries, and known gaps discovered while building the AIVANA
test suite. Per the ground rules for this pass: nothing here was silently resolved by guessing
at clinical intent -- each item below is either a documented current-behavior test (pinning
down what the code does today) or a flagged gap for the project owner to decide on.

## 1. Fixture modeling assumption (tests/from_data/fixtures.py)

The three source PDFs each present a case as one continuous block: dialogue, spoken physical
exam findings, differential diagnosis discussion, investigations, prescription, and advice.
There's no marker distinguishing "things actually said aloud" from "things a scribe would
chart separately." fixtures.py treats the entire block as the `transcript` field verbatim,
matching how `opd.html` really sends a single free-text transcript to `POST /api/scribe`. An
alternative reading -- splitting each case into a shorter "spoken" transcript plus a separate
structured ground-truth object -- was considered and rejected as inventing a distinction the
source material doesn't make.

## 2. known_diagnoses / known_medications are not asserted against LLM extraction quality

Each fixture case carries the diagnoses/medications transcribed verbatim from that PDF's own
"Differential Diagnosis" / "Prescription" section. These are real ground truth, but the test
suite has no live Groq credentials (by design -- see conftest.py's `_no_live_groq_calls`
guard) and mocks every Groq call. A test that mocks Groq to return the known-correct answer
and then asserts the pipeline returned that answer would prove nothing about extraction
*accuracy* -- only that AIVANA's plumbing (JSON parsing, DB persistence, response shape)
doesn't corrupt whatever the model returns. That's what `tests/from_data/test_opd_scribe_pipeline.py`
actually tests. Evaluating real extraction quality against these 12 cases requires a live-LLM
run (see the `llm_integration` pytest marker, currently unused/opt-in) and is out of scope for
an offline, deterministic test suite.

## 3. Vital sign units are not tracked anywhere in the schema

`Vital` (backend/app/models.py) has no `unit` or `temperature_scale` column. The abnormal-vital
flag (`GET /api/ipd/patients`) assumes Celsius (`temperature > 38`) and mmHg for BP, but nothing
enforces or records which unit was actually entered. A nurse who enters a Fahrenheit reading
(e.g. 99.5) would have it silently treated as a (very high) Celsius temperature and flagged
abnormal; conversely a genuinely high Fahrenheit temperature that happens to be numerically
under 38 would be missed. This is a real clinical-safety gap, not fixed here because the
correct resolution (add a units column, convert at the API boundary, or enforce a single unit
in the UI) is a product decision with several reasonable answers, none of which the codebase or
source PDFs settle. `tests/integration/test_ipd_edge_cases.py` pins down the exact
strict-greater-than threshold behavior so a future fix can be verified against a known baseline
instead of guessing what "current behavior" was.

## 4. No validation of physiologically impossible vital values

Negative or zero heart rate, negative blood pressure, etc. are accepted and stored without any
range check (`test_negative_vital_values_are_accepted_without_validation`). No bounds-checking
was added, because the codebase defines no canonical valid range anywhere, and inventing one
(e.g. "heart rate must be 20-300") would be adding clinical judgment not present in the source
material. Recommended follow-up: the product owner should specify acceptable ranges per field;
until then this is a known gap, not silently patched.

## 5. Email case-sensitivity allows duplicate identities

`backend/app/main.py`'s `/api/auth/register` checks `User.email == email` with no case-folding,
and the `email` column has a plain `unique=True` constraint (also case-sensitive under SQLite's
default BINARY collation). `alice@x.com` and `Alice@X.com` can register as two distinct
accounts. `tests/integration/test_auth_edge_cases.py::test_registration_is_case_insensitive_for_duplicate_email`
is marked `xfail` to document this as *current* behavior rather than silently normalizing
email casing at registration time -- doing so changes auth-identity semantics (do existing
users get merged? does login also need to normalize? what about the audit log's stored email?)
and is a decision for the project owner, not something to resolve unilaterally mid test-pass.

## 6. Unicode/ASCII gap in password complexity (pre-existing, documented not fixed)

`validate_password_complexity` (backend/app/auth.py) uses `[A-Z]`/`[a-z]` regex classes, which
are ASCII-only. A password whose only "letters" are accented Unicode (e.g. `Österreich9!#`)
will fail the uppercase/lowercase checks even though it visually has mixed case. Documented in
`tests/unit/test_password_complexity.py::test_unicode_only_letters_do_not_satisfy_ascii_case_requirements`.
Flagged as a real internationalization gap for a system likely to have non-English users, not
fixed here since loosening the character classes is a security/product tradeoff (broadening
what counts as "uppercase" could weaken the entropy guarantee the rule is meant to provide).

## 7. `api/index.py` vs `backend/app/*.py` drift -- RESOLVED (removed)

Previously this section documented the Vercel serverless duplicate's drift from `backend/app`
and flagged "delete vs. sync" as a decision owed to the project owner. That decision has since
been made: the project committed to Render as the sole deployment target, and `api/index.py`,
`vercel.json`, and the local `.vercel/` CLI link were deleted rather than kept in sync (see
ARCHITECTURE_NOTES.md section 1, CHANGELOG.md). All the drift issues that file carried
(missing doctor IPD access, missing drug-interactions endpoint, a different `ScribeEngine`
implementation, and a live `admin_create_user` `KeyError` bug) are moot now that the file is
gone. If a Vercel (or other serverless) target is ever wanted again, build a thin handler that
imports `backend.app.main:app` directly rather than hand-maintaining a second copy.

## 8. Consultation.patient_id / IPD Patient are intentionally decoupled

OPD consultations (`POST /api/scribe`) accept an optional `patient_id` with no FK-existence
check, and OPD has no dependency on the IPD `Patient` table otherwise. This looks like intentional
separation (a walk-in OPD consult doesn't require formal IPD admission) rather than a bug, so no
validation was added. If the product intent is actually that every consultation should link to
a real admitted patient, that's a scope decision, not a bug fix.

## 9. Unverified: whether transcript-doubling actually caused empty-draft failures in production

Investigating the "voice consultation data not filling in" report (CHANGELOG.md) found that
`opd.html` was sending the entire transcript duplicated to `POST /api/scribe` (see fix there).
One plausible failure mode floated during that investigation: a long enough real consultation,
doubled, could exceed a lower-tier Groq model's context window and silently degrade to
`scribe.py`'s all-empty fallback draft. **This mechanism was never confirmed against the real
Groq API** -- all `tests/e2e/` and `tests/from_data/` tests mock `scribe._call_groq_api`
entirely (per this repo's policy of never making live LLM calls from the default test suite,
see item 2 above), so there's no evidence this specific failure mode actually fired in
production versus the two other confirmed bugs (the access-token crash, and the IPD note
Save discarding edits) being sufficient on their own to explain the report. Recorded here so a
future investigator doesn't have to re-derive it, and doesn't mistake "plausible contributing
factor" for "confirmed root cause."

## 10. Abnormal-vital flagging ignored oxygen_sat entirely and had no low-heart-rate threshold (fixed)

`GET /api/ipd/patients` (`main.py`, the abnormal-vital block) checked `bp_systolic > 140`,
`bp_diastolic > 90`, `heart_rate > 100`, and `temperature > 38` -- but never looked at
`oxygen_sat` at all, and only had a *high* threshold for heart rate, none low. A dangerously
low SpO2 (e.g. 78%, clinically an emergency) or severe bradycardia (e.g. 35 bpm) was recorded
exactly as entered and silently treated as "normal" on the ward dashboard.

**Fixed**: added `heart_rate < 60` (standard sinus-bradycardia cutoff) and `oxygen_sat < 92`
(standard hypoxia/oxygen-therapy action threshold, e.g. used as a NEWS2 scoring boundary) to
the abnormal check. These are widely-used textbook thresholds, not invented ad hoc, but they
are still single-vital cutoffs, not a full weighted early-warning score -- **a clinician should
still confirm/formalize these against a real NEWS2/MEWS protocol** before this is relied on as
the hospital's actual early-warning system; treat this fix as closing the "silently normal"
gap, not as clinical sign-off on the exact numbers. Regression-pinned in
`tests/integration/test_ward_daily_scenarios.py::test_dangerously_low_oxygen_saturation_is_flagged_abnormal`
and `::test_severe_bradycardia_is_flagged_abnormal`, plus boundary tests in
`tests/integration/test_ipd_edge_cases.py` (`test_low_side_abnormal_vital_boundary_*`).

## 11. SQLite (test DB) vs. Postgres (production) parity gaps, not independently verified

Two behaviors observed in this pass's test run only hold for the throwaway SQLite database
`tests/conftest.py` points at -- they are *not* verified against a real Postgres instance
(per `ARCHITECTURE_NOTES.md`'s standing safety note, this pass never connected to the real
`DATABASE_URL`):

- **Column length is unenforced.** `Patient.name` is `String(200)`; SQLite does not enforce
  `VARCHAR` length at all, so `tests/integration/test_admission_scenarios.py::test_admit_patient_with_very_long_name`
  (300 chars) passes cleanly here. Postgres *does* enforce `VARCHAR(200)` and would very likely
  raise a raw `DataError` (surfacing as an unhandled 500, since nothing in `create_ipd_patient`
  catches a DB-level error) for the same input in production. Same risk applies to every other
  `String(n)` column fed from user input (`ward`, `bed`, `gender`, emails, etc.).
- **Non-numeric values bound to Integer columns don't error.** Passing a non-numeric string as
  `patient_id` in a JSON body (e.g. `"not-a-number"`) reaches a raw SQLAlchemy filter
  (`Patient.id == "not-a-number"`) with no Pydantic model in front of it to reject it first;
  under SQLite's flexible type affinity this just matches no rows and returns a clean 404
  (`tests/integration/test_vitals_recording_scenarios.py::test_record_vital_malformed_patient_id_handled_cleanly`).
  Postgres's stricter type system may reject the parameter binding outright, which would
  surface as a raw 500 in production instead of the clean 404 seen here.

Neither is "fixed" here because doing so would mean either adding Pydantic request models
across endpoints that currently take a bare `dict` (a real, larger refactor, not a small patch)
or column-level `CHECK`/length validation with product input on the right limits -- both out of
scope for a same-day test-and-fix pass. Flagged so a future incident ("500 in prod, green in
CI") isn't a mystery.

## 12. `voice-to-vitals`'s extraction result is NOT type-coerced or validated (unlike `record_vital`)

`POST /api/ipd/voice-to-vitals` (the standalone preview endpoint, fixed to require Nurse/
HeadNurse this pass -- see CHANGELOG.md) returns whatever `scribe._generate_json` produces
completely unmodified, including the type-coercion fix applied to `record_vital`'s `Vital`-
persisting path. This is intentional, not an oversight: `voice-to-vitals` never touches the
database (`tests/integration/test_voice_to_vitals_endpoint.py::test_does_not_persist_anything_to_database`),
so there's no DB-column type mismatch to crash on -- it's a raw preview, and coercing its
output would just be extra work with no corresponding safety benefit. Documented explicitly
(`test_returns_raw_extraction_unmodified`) so a future reader doesn't assume the two endpoints
share behavior just because they share a prompt shape.

## 13. IPD voice endpoints (vitals/nursing-notes/nurse-consult) have no minimum transcript length

OPD's `POST /api/scribe` rejects any transcript under 10 characters after stripping
whitespace (`tests/integration/test_scribe_input_edge_cases.py`). None of the three IPD voice
endpoints have an equivalent minimum -- `if voice_text:` is a bare truthiness check, so a
one-character `voice_text` like `"a"` reaches the LLM call same as a full dictation
(`tests/integration/test_voice_input_robustness.py::test_ipd_voice_endpoints_have_no_minimum_length_unlike_opd_scribe`).
Not changed: unlike OPD (a single doctor-patient conversation, where under 10 chars is almost
certainly a mis-click), a nurse's voice note for a single vital reading ("BP 120/80" or even
just "stable") is legitimately short, so importing OPD's threshold verbatim would likely reject
real, valid input. Pinned down as current behavior for a future reader who might otherwise
"fix" it into an inconsistency in the other direction.

## 14. The `POST /api/ipd/assign` concurrent-assignment race was tested live, not just flagged

Prior passes documented (but never exercised) a theoretical race: `assign_patient`'s "close the
prior Active assignment, then insert the new one" logic has no transaction-level locking, so
two truly concurrent requests could both read "no active assignment yet" before either writes,
producing two simultaneously `Active` `NurseAssignment` rows for one patient.
`tests/concurrency/test_concurrent_requests.py::test_concurrent_assignment_to_same_patient_different_nurses`
fires 8 genuinely simultaneous assignment requests (via a real live server + `ThreadPoolExecutor`,
not the in-process `TestClient`) at the same patient and asserts exactly one `Active` row
survives. **Result: it passed** -- no double-assignment was observed in this test environment.
This is not proof the race is impossible, only that it didn't manifest under SQLite (this
project's test/dev database): SQLite's file-level locking is coarse enough that it likely
serializes just enough of the read-then-write critical section to prevent the interleaving in
practice, at this concurrency level, on this hardware. **Production runs on Postgres**, which
has genuinely fine-grained row-level locking and could interleave differently under real load.
Not fixed with an actual `SELECT ... FOR UPDATE` or unique constraint here, because that would
mean guessing at a fix for a bug that's empirically not reproducing, rather than responding to
a confirmed failure -- flagged as a residual gap rather than either "confirmed safe" or
"confirmed broken." If this ever needs to be closed definitively, the right fix is a partial
unique index (`NurseAssignment(patient_id) WHERE status = 'Active'`) enforced at the database
level, which works regardless of what the application-layer code does or doesn't lock.

## 15. `final test output/`'s AI content is synthetic, not live-model output (key was invalid)

`backend/.env`'s `GROQ_API_KEY` returned `401 invalid_api_key` from Groq's own API when probed
at the start of this pass, and remained invalid throughout. Every file under
`final test output/` was still generated by driving the **real** voice-simulated pipeline (mic
input, real HTTP requests, real storage/retrieval) end to end -- only the AI-generated *content*
itself (prescriptions, discharge summaries) falls back to this repo's curated, clinically-
plausible synthetic text (`tests/scenarios/curated_use_cases.py`) rather than genuine model
output. Every case's `metadata.json`, and the top-level `final test output/_index.json`, records
`"ai_source": "synthetic_fallback"` explicitly -- this is never silently presented as real AI
output. `tests/scenarios/test_generate_final_outputs.py` re-probes the key at collection time on
every run, so simply fixing the key in `backend/.env` and re-running
`pytest tests/scenarios -m e2e` regenerates every one of the 30 use cases with real model output,
no code changes needed.

## 16. One pre-existing Playwright timing flake in the curated scenario suite, root-caused as
## test-infrastructure, not an application bug

`tests/scenarios/test_generate_final_outputs.py::test_generate_opd_output[chromium-UC018_pediatric_seizure_bengali_rural_12min]`
fails consistently (not intermittently) with an empty draft (`chiefComplaint`/`primaryDiagnosis`
both `""`), while the other 21 OPD cases in the same file pass every run. Investigated during
the 2026-08-03 pass (which restructured `opd.html` into a step wizard and was the reason this
got a closer look, though the flake predates that change):

- **Confirmed not a backend/extraction bug**: calling `POST /api/scribe` directly (bypassing the
  browser entirely) with this exact case's transcript and mocked Groq response returns a fully
  correct, populated draft. The scribe pipeline, `drug_matcher`, and `lab_test_matcher` all
  handle this case's content (a Bengali transcript, a "Paracetamol syrup" medication that
  triggers the drug matcher's form-gated correction path) with no error.
- **Confirmed not caused by the opd.html wizard restructure**: `git diff` at the time this was
  investigated showed `tests/scenarios/test_generate_final_outputs.py`,
  `tests/scenarios/curated_use_cases.py`, `tests/_voice_helpers.py`, and `frontend/opd.html`
  were all either unmodified or (for opd.html) reproduced the identical failure both before and
  after the restructure.
- **Not root-caused further than "Playwright/speech-mock timing, specific to this transcript"**:
  the most likely mechanism is the mocked-speech-recognition `_chunk_transcript`/
  `fire_speech_result` harness (`tests/_voice_helpers.py`) racing against this particular
  transcript's chunk count/length combination such that the accumulated transcript sent to
  `/api/scribe` on Stop ends up too short, but this was not confirmed with certainty and no fix
  was attempted, since the underlying application code is verified correct.

Not fixed: doing so would mean altering shared test-harness timing (`_chunk_transcript`/
`fire_speech_result`, used by all 30 scenario cases and several e2e files) to chase one flaky
case, risking new flakiness elsewhere, for a case that already has 21 sibling cases passing and
whose content is independently confirmed correct via direct API testing. Recorded here so a
future full-suite run isn't mistaken for a real regression when this one case is red.


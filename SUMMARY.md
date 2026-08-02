# SUMMARY.md

Final summary of the AIVANA test-and-fix work, current through 2026-08-01's full-application
pass. Five passes total: 2026-07-31 part 1 (general ward-workflow hardening), 2026-07-31 part 2
(voice-feature hardening), 2026-08-01 part 1 (complete HeadNurse end-to-end testing +
convenience features), 2026-08-01 part 2 (complete NursingStation end-to-end testing),
2026-08-01 part 3 (complete cross-role application testing, new Discharge Summary feature,
critical security fix, real concurrency testing, curated multi-lingual use-case library). See
ARCHITECTURE_NOTES.md for the codebase map, CHANGELOG.md for the full chronological fix log,
and TEST_NOTES.md for ambiguities/gaps deliberately left undecided rather than guessed at.

## Scope of the 2026-07-31 pass, part 1: general ward workflow

Prior passes covered auth, multi-tenant isolation, OPD scribe parsing, and three real-browser
voice-consultation bugs (144 tests total going in). This pass targeted the specific scenario
the product exists for: a busy ward day where a head nurse assigns patients to nurses, nurses
record vitals and examine patients throughout the day, tasks get created and completed, and
patients eventually discharge. Read every backend endpoint and both `frontend/ipd.html` and
`frontend/admin.html` line by line before writing anything, which surfaced real bugs no prior
pass had touched — in particular, no existing test exercised `POST /api/ipd/nurse-consult` at
all before this pass.

## What was fixed this pass

1. **`POST /api/ipd/nurse-consult` double-persisted every voice consult.** It wrote an
   unreviewed AI draft (Vital rows with every structured column null, plus a NursingNote) to
   the database immediately on "Process", before the nurse ever reviewed it in the UI —
   duplicated by the real, reviewed Save if the nurse proceeded, or left behind as an orphaned,
   un-reviewed ghost record in the permanent chart if they didn't. Fixed by making the endpoint
   a pure preview/extraction step with zero database writes.
2. **Voice-recorded vitals never populated the columns the UI/dashboard actually read.**
   `ipd.html`'s Save handler sent every vital with `bp_systolic`/`heart_rate`/etc. hardcoded to
   `null`, with the real reading buried in a free-text `notes` string — so the abnormal-vitals
   alert never fired for anything captured via the voice flow, and the patient chart literally
   rendered "BP null/null | HR null". Fixed with a frontend parameter-name mapper
   (`mapVitalsToStructured`) that populates the real numeric columns in one consolidated POST.
3. **Voice-derived vitals/nursing-notes silently saved blank on extraction failure**, with a
   plain 200 "success" and no signal to the nurse that nothing was actually captured. Both
   endpoints now return 422 when extraction (or a manual empty submission) yields nothing
   usable, while still accepting genuinely partial data unchanged.
4. **`create_task`'s `nurse_id` had no existence/role/organization validation**, unlike its
   sibling `assign_patient`. A typo'd id, a Doctor's id, or a cross-org nurse id was silently
   stored, producing a task nobody could ever see or complete. Now validated the same way.
5. **Discharging/transferring a patient never closed their active nurse assignment**, so a
   discharged patient kept appearing in that nurse's ward list indefinitely. Fixed with a
   cascade on any status change away from `"Active"`, plus a defense-in-depth status filter on
   the nurse's own roster query.
6. **No discharge workflow existed in the UI at all** — the only "Edit Patient" action sent
   ward/bed/diagnosis, never status, even though the backend already supported it.
7. **No way to see which nurse was assigned to which patient**, anywhere in the API or UI — a
   head nurse managing a ward's assignments had no roster visibility beyond opening each
   patient individually and still not being told. Added `assigned_nurse` to the roster and
   patient-details responses, and nurse-email attribution on vitals/tasks/nursing notes.
8. **A dev-dependency version mismatch broke the entire test suite before any of the above
   could even be verified**: `httpx==0.28.1` dropped the `app=` constructor shortcut this
   project's pinned `starlette==0.27.0` `TestClient` relies on. Pinned `httpx<0.28`.
9. **Self-caught during this same pass**: the new `assigned_nurse.email` field came back `null`
   whenever a patient had an assignment but no vitals/tasks/notes yet, because the lookup dict
   that resolves nurse ids to emails didn't include the assignment's own nurse id. Caught by
   a test written in this pass before it ever shipped, fixed immediately.

## What was added (features, beyond bug fixes)

- Discharge action in the patient detail modal (HeadNurse/NursingStation only).
- `assigned_nurse` visibility on the ward roster, patient detail, and the assign dropdown (so a
  head nurse sees who already has a patient before reassigning); unassigned patients flagged.
- Overdue-task flagging (`is_overdue` per task, `overdue_tasks` count on the roster), surfaced
  as a dashboard alert and highlighted rows in both the patient-detail and global task views.
- Patient search/filter box on the Patients list (name/ward/bed) for wards with a large roster.
- Nurse-email attribution in place of raw numeric ids throughout the vitals/tasks/notes views.

## What was added (tests)

~250 new tests across 9 new integration files plus 1 new e2e file, on top of the 144
pre-existing tests:

- `test_role_permission_matrix.py` — full 5-role x 16-endpoint permission matrix, plus
  unauthenticated/garbage-token rejection.
- `test_nurse_consult_no_persistence.py`, `test_voice_extraction_failure_guards.py`,
  `test_task_nurse_assignment_validation.py`, `test_discharge_workflow.py`,
  `test_assigned_nurse_visibility.py` — regression coverage for each fix/feature above.
- `test_ward_daily_scenarios.py`, `test_vitals_recording_scenarios.py`,
  `test_admission_scenarios.py`, `test_task_lifecycle_scenarios.py` — realistic multi-step
  ward-day sequences, boundary/decimal/unicode input, and documented (not invented) gaps.
- `tests/e2e/test_ipd_vitals_mapping_and_discharge.py` — real-browser coverage for fixes #1/#2.

See CHANGELOG.md's 2026-07-31 (part 1) entry for the full per-file rationale.

## Scope of the 2026-07-31 pass, part 2: dedicated voice-feature hardening

Explicit follow-up request: confirm the voice-based features nurses actually use (mic ->
Groq extraction -> vitals / nursing notes / full consult) had been run at real scale, not just
covered incidentally by part 1's broader ward tests. They hadn't — part 1 left ~33 voice-
specific cases, enough to catch the persistence and empty-save bugs but no systematic sweep of
extraction-result shapes or raw transcript content. Built that sweep (~214 new cases, landing
total voice-specific coverage at ~247, within the requested 200-300 range) and it found two
more real, previously-unknown crash bugs:

1. **`scribe._generate_json` didn't enforce its own `-> dict` return type.** Valid JSON that
   happens to parse to a list/string/number ("[1, 2, 3]", "true") skipped the existing
   JSON-decode-failure fallback entirely (it's not a decode error) and got returned as-is —
   every caller's immediate `.get(...)` then crashed with a raw `AttributeError`. Reproduced
   live via `POST /api/ipd/vitals` before fixing. One fix at the source (route non-dict results
   through the same fallback as a decode failure) protects all three voice endpoints at once.
2. **`record_vital`'s voice path crashed on non-numeric field types from the LLM** instead of
   degrading gracefully — a list value crashed the SQLite insert outright
   (`sqlite3.ProgrammingError`), reproduced live before fixing; a non-numeric string would have
   silently corrupted later numeric comparisons (the abnormal-vitals check). Added a
   best-effort `_coerce_number()` helper that extracts a usable number or returns `None`,
   applied before the existing empty-extraction 422 guard runs.
3. **`POST /api/ipd/voice-to-vitals` had no role check at all** — any authenticated role
   (Admin, Doctor, NursingStation) could call this Groq-backed extraction endpoint, unlike its
   siblings. Fixed to match (Nurse/HeadNurse only). Low severity (no persistence) but a real
   inconsistency, caught only because every voice-capable endpoint was swept systematically.

New files: `test_voice_vitals_extraction_scenarios.py` (42), `test_voice_nursing_note_extraction_scenarios.py`
(32), `test_voice_nurse_consult_extraction_scenarios.py` (41), `test_voice_to_vitals_endpoint.py`
(20), `test_voice_input_robustness.py` (71, unicode/RTL/control-character/injection-shaped
transcript sweeps across all three persisting voice endpoints), and
`tests/e2e/test_ipd_voice_mic_lifecycle.py` (8, real-browser mic button lifecycle including a
full speak -> Process -> nurse-corrects-the-extraction -> Save round trip). See CHANGELOG.md's
part 2 entry for full detail.

## Scope of the 2026-08-01 pass, part 1: complete HeadNurse end-to-end testing + convenience features

Explicit follow-up request: complete end-to-end testing of the HeadNurse role specifically
(every functionality, including voice, at 200-300 dedicated cases) plus "think as a head nurse"
and add convenience features on top, testing those too. Before writing any tests, audited every
role-gated UI element in `ipd.html` against the backend's actual permission checks (the same
method that found part 1's nurse-consult bug) — this surfaced three real bugs, two of them
UI-only permission mismatches specific to HeadNurse, and one a role-independent HTML `id`
collision that had silently broken a core feature (the patient-detail Tasks tab) for *every*
role, not just HeadNurse, with zero error signature:

1. The Admit Patient button was only ever shown for `NursingStation`, despite the backend
   always allowing `HeadNurse` too — a head nurse had no UI path to admit a patient at all.
2. The Mark Complete task button was only ever shown for the assigned `Nurse` (in both places
   it's rendered), despite the backend always allowing `HeadNurse` to complete *any* task.
3. **The sidebar's "Tasks" nav button and the patient-detail modal's Tasks tab-content div
   shared the same `id="tasks-tab"`.** `getElementById` always resolved to the sidebar button
   (first in DOM order), so the tab-switch handler was silently toggling the wrong element's
   style — the real tab content stayed `display:none` forever after being hidden by the same
   handler's own "hide all tabs" step. Found only because a test attempted a genuine
   `.click()` (which requires real visibility) rather than a DOM-presence check.

Convenience features added, thought through from a head nurse's actual daily-oversight
perspective: `POST /api/ipd/unassign` (explicitly close an assignment without picking a
replacement — e.g. a nurse goes home sick), `GET /api/ipd/nurse-workload` (active-patient count
per nurse, surfaced in the Assign dropdown so assignments aren't made blind to who's already
overloaded), a ward summary stat bar on the Dashboard (total/unassigned/abnormal/overdue
counts), and priority sorting of the dashboard grid (abnormal vitals first, then overdue tasks).

New files: `test_headnurse_full_workflow.py` (22), `test_headnurse_permission_boundaries.py`
(31), `test_headnurse_admit_and_assign_scenarios.py` (31), `test_headnurse_task_management.py`
(24), `test_headnurse_voice_features.py` (24), `test_headnurse_voice_input_robustness.py` (51),
`test_headnurse_vitals_and_notes.py` (23), `test_headnurse_dashboard_data_scenarios.py` (10),
`tests/e2e/test_headnurse_e2e_workflow.py` (14), `tests/e2e/test_headnurse_voice_e2e.py` (7) —
237 dedicated HeadNurse cases total, within the requested 200-300 range. See CHANGELOG.md's
2026-08-01 (part 1) entry for full detail.

## Scope of the 2026-08-01 pass, part 2: complete NursingStation end-to-end testing

Same-day follow-up: the "ward login" (NursingStation) also needed complete end-to-end testing
at 200-300 dedicated cases. Confirmed against `main.py` that this is the narrowest role in the
system — exactly six endpoints check `is_nursing_station()`: admit, update/discharge, ward-wide
roster, patient details, and read-only vitals/tasks. No clinical recording (vitals, tasks,
notes, any voice feature) and no nurse-assignment management of any kind.

Ran the same UI-permission audit as the HeadNurse pass before writing tests. Unlike that pass,
**this one found zero new bugs** — the two HeadNurse-pass fixes (the Admit button, and the
`tasks-tab` id collision) already fully covered every surface NursingStation shares with
HeadNurse, confirmed via `tests/e2e/test_nursingstation_e2e_workflow.py`. Recorded as a
meaningful result in its own right: a systematic audit turning up nothing on a second pass
confirms the first pass's fixes generalized correctly, rather than indicating the audit wasn't
thorough.

New files: `test_nursingstation_full_workflow.py` (12), `test_nursingstation_permission_boundaries.py`
(29), `test_nursingstation_admission_scenarios.py` (42, the deepest coverage since admission is
this role's core daily duty — every specialty ward, full age range, a 30-patient admission-rush
scenario), `test_nursingstation_patient_management.py` (13), `test_nursingstation_dashboard_and_read_access.py`
(15), `test_nursingstation_denial_consistency.py` (40, proves the role check fires before body
validation on every denied endpoint), `test_nursingstation_voice_feature_denial.py` (37, denial
holds regardless of transcript content, with an explicit assertion Groq is never invoked),
`test_nursingstation_realistic_scenarios.py` (18, multiple front-desk operators sharing one
roster, realistic intake data, a representative full day), and
`tests/e2e/test_nursingstation_e2e_workflow.py` (13) — 219 dedicated NursingStation cases total,
within the requested 200-300 range. See CHANGELOG.md's 2026-08-01 (part 2) entry for full detail.

## Scope of the 2026-08-01 pass, part 3: full-application testing, new feature, critical fix

The broadest single request of this engagement: complete application testing across every
login type and use case *combined* (not per-role in isolation), scenarios from a single-doctor
small clinic to a multi-specialty hospital and trauma center, the full clinical breadth
(trauma/emergency through chronic disease, rare disease, multiple cancer types, IVF, cosmetic
care), real concurrent/bulk-load testing, a new AI-generated Discharge Summary feature, and a
curated multi-lingual use-case library driven through the real voice UI with saved output
artifacts.

**Most severe finding of the entire engagement**: `GET /api/auth/users`,
`PATCH /api/auth/users/{id}`, and `PATCH /api/auth/users/{id}/password` had no
organization-scoping at all — any Admin could enumerate every user across every organization,
change any other organization's user's role, or **reset any other organization's user's
password** (complete cross-tenant account takeover). Found via an unrelated hospital-scale
scenario test unexpectedly returning one extra user. All three fixed with the same org filter
pattern already used everywhere else in the codebase; 10 regression tests added.

**New feature**: AI-generated Discharge Summary (`POST`/`GET /api/ipd/patients/{id}/discharge-summary`),
assembling a patient's vitals trend, nursing notes, tasks, and linked OPD consultations into a
structured discharge document — a genuine hospital-operations pain point (manually writing
discharge paperwork from the chart) addressed with data this system already captures. Includes
a print/export view mirroring OPD's existing prescription-print pattern. 22 new tests.

**Real concurrency testing** (new `tests/concurrency/`, 10 tests): genuine simultaneous HTTP
requests against a live server, not the in-process `TestClient`. Specifically targeted the
previously-theoretical `POST /api/ipd/assign` race — 8 concurrent assignment calls to the same
patient still produced exactly 1 `Active` assignment (didn't reproduce under SQLite; caveat
about Postgres's finer-grained locking documented in TEST_NOTES.md). Also verified: concurrent
vitals recording (no data loss), 50-patient bulk concurrent admission (no ID collisions), 20
simultaneous logins, account lockout under concurrent failed attempts, and a 50-request mixed
read/write burst (zero 5xx responses).

**~330 new large-scale functional cases**: 35 clinical-specialty scenarios spanning every
requested specialty (trauma, chronic disease, 5 rare diseases, 5 cancer types, IVF, cosmetic
dermatology, infectious disease, psychiatry, and more) through the real OPD scribe pipeline;
hospital-scale scenarios from a single-doctor clinic to a 30-patient 10-ward multi-specialty
hospital and a 25-patient trauma-center mass-casualty surge; multi-visit diagnostic workup
journeys where a diagnosis firms up across several consultations.

**Curated multi-lingual use-case library** (new `tests/scenarios/`, output in
`final test output/`): 30 use cases (22 OPD + 8 multi-day IPD stays) spanning small rural
clinic to multi-specialty urban hospital to trauma center, ~5-25 minute consultations, and 14
language variants covering the major languages spoken across India (Hindi, Bengali, Telugu,
Marathi, Tamil, Gujarati, Urdu, Kannada, Odia, Malayalam, Punjabi, Assamese, English, Hinglish).
Each is driven through the **real voice-simulated UI** (mic → speech → Start/Stop Consulting or
Process/Save), not a raw API call. **AI content note**: the configured Groq API key was invalid
throughout this pass, so structured output (prescriptions/discharge summaries) uses this
project's curated synthetic content instead of live model output — every output file's
`metadata.json` says so explicitly (`"ai_source": "synthetic_fallback"`), never presented as
real AI output. The full pipeline (voice input, HTTP requests, storage, retrieval) ran for
real regardless; fixing the API key and re-running `pytest tests/scenarios -m e2e` regenerates
every case with genuine model output, no code changes needed.

See CHANGELOG.md's 2026-08-01 (part 3) entry for the complete file-by-file breakdown.

## Current test coverage

1309 tests across `tests/unit/` (pure-function logic), `tests/from_data/` (12 real-transcript
OPD pipeline cases), `tests/concurrency/` (real simultaneous-request testing), `tests/scenarios/`
(the curated multi-lingual use-case library), `tests/integration/` (multi-tenant isolation,
auth, PHI leakage, the full IPD ward workflow, dedicated HeadNurse/NursingStation-role suites,
clinical-specialty diversity, hospital-scale scenarios, diagnostic workups, and the critical
user-management isolation fix), and `tests/e2e/` (real headless-browser coverage of every major
UI flow, including the new Discharge Summary feature). All confirmed passing together in one
full run at the end of this pass (only 1 intentional `xfail`, documenting the pre-existing
email-case-sensitivity gap). All target `backend/app`, the sole deployable service.

## Remaining risks / known gaps (not fixed, documented in TEST_NOTES.md)

- **`Vital` has no unit field** (Celsius/Fahrenheit, mmHg assumed) — pre-existing gap, unchanged.
- **No physiological-range validation** on vitals or patient age — negative/impossible values
  accepted and stored as-is.
- **Abnormal-vital flagging never checks `oxygen_sat` at all, and has no low-heart-rate
  threshold** — found this pass. A dangerously low SpO2 or severe bradycardia is silently
  "normal" on the ward dashboard. Not fixed: this is a clinical early-warning-score decision
  (effectively half of a NEWS2/MEWS score) that needs clinician sign-off, not an invented cutoff.
- **Email comparison is case-sensitive** — pre-existing gap, unchanged (`xfail`-documented).
- **Password complexity's case checks are ASCII-only** — pre-existing gap, unchanged.
- **SQLite-vs-Postgres parity not independently verified**: column-length enforcement and
  non-numeric-value type coercion behave differently between the test DB (SQLite) and
  production (Postgres) for a handful of endpoints that take raw `dict` bodies with no Pydantic
  model in front of them. Found and documented this pass (TEST_NOTES.md section 11); not fixed,
  since a real fix means adding request-validation models across those endpoints, a larger
  refactor than a same-day test pass should take on unilaterally.
- **Concurrent-assignment race** (`POST /api/ipd/assign` has no locking) was tested live under
  real concurrency this pass and did not reproduce a double-assignment under SQLite — but this
  is not a guarantee under Postgres's finer-grained row locking in production (TEST_NOTES.md
  section 14). Not fixed with a DB-level constraint, since that would mean patching a bug that
  isn't confirmed to occur, rather than responding to a demonstrated failure.
- **`final test output/`'s AI content is synthetic, not live model output** — the configured
  Groq API key was invalid throughout this pass. Every case's `metadata.json` says so
  explicitly; fixing the key and re-running `pytest tests/scenarios -m e2e` regenerates
  everything with real AI output (TEST_NOTES.md section 15).

## Suggested next steps

1. **Fix `backend/.env`'s `GROQ_API_KEY`** (currently invalid — `401 invalid_api_key`) and
   re-run `pytest tests/scenarios -m e2e` to regenerate `final test output/`'s 30 use cases
   with real AI-generated content instead of the current synthetic fallback.
2. Get clinical (not engineering) sign-off on an early-warning vital-sign scoring scheme
   (ideally NEWS2/MEWS-style, covering SpO2 and low-heart-rate thresholds, not just the four
   ad hoc high-value checks that exist today), then encode it as both a schema/logic change and
   tests.
3. Decide on vital-sign units and physiological range validation (vitals and age) with clinical
   input — same open question as prior passes, still unresolved.
4. Add Pydantic request models to the handful of endpoints still taking a bare `dict` body, to
   close the SQLite/Postgres parity gap found in an earlier pass (TEST_NOTES.md section 11)
   rather than discovering it via a production 500.
5. If a real (not test) Postgres instance is available, re-run
   `tests/concurrency/test_concurrent_requests.py`'s assignment-race test against it — the
   SQLite result this pass got (no race observed) is not a production guarantee (TEST_NOTES.md
   section 14).
6. Consider whether email should be case-folded at registration/login (prior-pass open question,
   still unresolved).
7. Consider whether `scribe.py`'s full-transcript `print()` logging should move to structured,
   redacted logging (prior-pass open question, still unresolved).
8. If Render deployment isn't already configured via an in-repo `render.yaml`, consider adding
   one so the deployment config is version-controlled rather than living only in Render's
   dashboard (prior-pass suggestion, still unresolved).

## Exit criteria status

- [x] 100% of tests derived from `./data` pass (39/39 in `tests/from_data/`).
- [x] 100% of pre-existing tests still pass (no regressions across 1309 total tests, confirmed
      in one full combined run at the end of this pass).
- [x] No unhandled exceptions/crashes across all tested scenarios, including edge cases —
      including two crash bugs found only by an earlier voice-specific sweep, a role-independent
      HTML id collision found only by the HeadNurse e2e pass, and (this pass) a **critical
      cross-tenant account-takeover vulnerability** across three user-management endpoints —
      none of which earlier, narrower testing had surfaced.
- [x] Every real bug found (including one caught in this pass's own new code before shipping)
      was fixed and pinned down with a regression test, or explicitly documented as a gap
      requiring a product/clinical decision rather than silently guessed at.
- [x] Real concurrent/bulk-load behavior verified against a live server, not just discussed as
      a theoretical concern.
- [x] A curated, multi-lingual, voice-driven use-case library exists with saved output
      artifacts, clearly labeled with its actual AI-content source.
- [x] All known ambiguities documented in TEST_NOTES.md, not silently resolved.
- [x] ARCHITECTURE_NOTES.md and CHANGELOG.md up to date.
- [x] This SUMMARY.md updated.

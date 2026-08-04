"""
Standalone (non-pytest) resumable runner for the large-scale voice-input test pass.

Not pytest-collected on purpose: thousands of individually-parametrized pytest tests would
add unreasonable collection/reporting overhead at this scale. This reuses the exact same
"simulate voice input" mechanics tests/e2e/ uses (tests/_voice_helpers.py) -- a real headless
browser with a mocked MediaRecorder -- against the REAL live Groq API for the
extraction/interaction/discharge chat-completion calls (unlike pytest's tests/conftest.py,
which deliberately blocks live calls).

Whisper transcription is the one exception, deliberately never live here: app.scribe.
transcribe_audio is set to return each scenario's own utterance text directly (see
_drive_opd_consult/_drive_ipd_round) rather than routed through a real Groq Whisper call.
This scenario library is built from synthesized utterance TEXT, not real recorded audio, so
there is nothing for a real Whisper call to transcribe -- and even if there were, pacing a 4th
real per-visit Groq call against a separate, model-specific rate-limit budget (see
RequestBucket) would need its own probe/budget entry for no real signal, since this harness
was never going to be able to validate live ASR accuracy against synthesized text anyway. This
means a scale run validates pipeline integrity and real extraction/interaction/discharge
quality end-to-end, not Whisper transcription accuracy on real Hindi/Hinglish speech.

Safety: always runs against a throwaway SQLite database, never the production Postgres URL
configured in backend/.env -- asserted defensively before and after import.

Usage:
    python -m tests.scale.runner --smoke 5              # ~25 cases, one per category, for validation
    python -m tests.scale.runner --total-cases 500       # a scaled-down proportional run, resumable
    python -m tests.scale.runner --categories OPD,EDGE   # only these categories
    python -m tests.scale.runner --resume                # (default) skip test_ids already in results.jsonl
"""
import argparse
import json
import os
import re
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(REPO_ROOT))

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_PATH = RESULTS_DIR / "results.jsonl"

ESTIMATED_TOKENS = {
    # The configured model is a reasoning model -- a real measured call (system+user prompt
    # of a simple 1-drug transcript) used ~1945 completion tokens (1733 of it hidden
    # reasoning) before reasoning_format=hidden was even applied to keep it that low; these
    # estimates intentionally sit above the single-case measurement to cover longer/multi-
    # drug transcripts without under-pacing the rate limiter into 429s.
    "extraction": 2200,   # scribe_transcript / IPD round extraction call
    "interaction": 1200,  # drug-interaction check
    "discharge": 2200,    # discharge summary generation
}


class RequestBucket:
    """Paces Groq calls to the REAL binding constraint: a per-model daily request quota that
    refills continuously rather than per-minute. Defaults are calibrated for
    llama-3.1-8b-instant (14,400 requests/day, verified live -> ~1 request per 6 seconds
    sustained, confirmed via x-ratelimit-reset-requests at near-full remaining). The
    reasoning-model this app shipped with (qwen/qwen3.6-27b) was ~1000/day (~1 request per 86
    seconds) -- pass --rate-requests-per-sec / --request-budget-capacity to match whatever
    model is actually configured if it changes again. Every extraction/interaction/discharge
    call must pass through this before the (much less restrictive) TokenBucket -- otherwise
    the run just spends its time hammering into 429s instead of pacing correctly."""

    def __init__(self, rate_per_sec=1.0 / 6.0, capacity=14000.0, starting_tokens=None):
        self.rate = rate_per_sec
        self.capacity = capacity
        self.tokens = capacity if starting_tokens is None else min(capacity, starting_tokens)
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, amount=1.0):
        with self.lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
                self.last = now
                if self.tokens >= amount:
                    self.tokens -= amount
                    return
                time.sleep(min((amount - self.tokens) / self.rate, 30))


class TokenBucket:
    """Secondary pacing against the token-level budget (refills fast, rarely binding once
    RequestBucket is in place, kept as defense-in-depth)."""

    def __init__(self, rate_per_sec=133.0, capacity=8000.0):
        self.rate = rate_per_sec
        self.capacity = capacity
        self.tokens = capacity
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, amount):
        with self.lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
                self.last = now
                if self.tokens >= amount:
                    self.tokens -= amount
                    return
                time.sleep((amount - self.tokens) / self.rate)


def _probe_groq_limits(safety_margin_requests=20, token_safety_factor=0.75):
    """Groq's request AND token-per-minute quotas both drain from whatever this key has
    already been used for today, and both are MODEL-SPECIFIC -- verified live, switching
    models from qwen3.6-27b (8000 TPM) to llama-3.1-8b-instant (6000 TPM) silently left the
    token bucket paced ~33% too fast for the new model's real limit, causing a wave of 429s
    the request-count budget alone didn't explain (it still had ~14,399/14,400 remaining at
    the same moment). Ask Groq directly for both current limits rather than hardcoding either,
    so this doesn't go stale again next time the model changes. token_safety_factor leaves
    headroom against burst timing (a case makes 2+ calls close together, not evenly spread)."""
    import requests as _requests
    from app.config import settings

    try:
        headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": settings.GROQ_MODEL, "messages": [{"role": "user", "content": "OK"}], "max_tokens": 3}
        resp = _requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=15)
        remaining_requests = int(resp.headers.get("x-ratelimit-remaining-requests", 0))
        limit_tokens = int(resp.headers.get("x-ratelimit-limit-tokens", 6000))
        return {
            "starting_requests": max(0, remaining_requests - safety_margin_requests),
            "token_rate_per_sec": (limit_tokens / 60.0) * token_safety_factor,
            "token_capacity": limit_tokens * token_safety_factor,
        }
    except Exception as exc:
        print(f"Could not probe real Groq limits ({exc}); falling back to conservative defaults.")
        return None


def _bootstrap_app():
    os.chdir(BACKEND_DIR)  # config.py's relative ".env" path resolves from here
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    db_path = Path(tempfile.mkdtemp(prefix="aivana_scale_db_")) / "scale_run.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ.setdefault("SECRET_KEY", "scale-run-secret-not-for-production")
    os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

    from app import main as app_main
    from app.config import settings

    assert "postgres" not in settings.DATABASE_URL.lower(), (
        "Refusing to run: DATABASE_URL resolved to a non-SQLite URL. This must never touch "
        "the production database."
    )
    if not settings.GROQ_API_KEY:
        print("WARNING: GROQ_API_KEY is empty -- Groq calls will fail. Check backend/.env.")
    return app_main


def _make_user(app_main, db, email, role, org_id=None):
    from types import SimpleNamespace
    from app.models import Organization, User, PasswordHistory
    from app import auth as app_auth

    if org_id is None:
        org = Organization(name="AIvana Scale Test Org")
        db.add(org)
        db.flush()
        org_id = org.id
    pw_hash = app_auth.get_password_hash("Str0ng!Passw0rd#1")
    user = User(email=email, password_hash=pw_hash, role=role, organization_id=org_id, status="Active")
    db.add(user)
    db.flush()
    db.add(PasswordHistory(user_id=user.id, password_hash=pw_hash))
    db.commit()
    db.refresh(user)
    # Detach as a plain snapshot -- the session this was created on is closed right after
    # setup_users() returns, and SQLAlchemy expires ORM object attributes on commit by
    # default, so holding onto `user` itself would raise DetachedInstanceError the next time
    # anything (e.g. mint_tokens) touches .id/.email/.role/.organization_id later in the run.
    return SimpleNamespace(id=user.id, email=user.email, role=user.role, organization_id=user.organization_id)


def setup_users(app_main):
    db = app_main.SessionLocal()
    try:
        doctor = _make_user(app_main, db, "doctor@scale-test.aivana", "Doctor")
        org_id = doctor.organization_id
        nursing_station = _make_user(app_main, db, "station@scale-test.aivana", "NursingStation", org_id)
        head_nurse = _make_user(app_main, db, "head@scale-test.aivana", "HeadNurse", org_id)
        nurse = _make_user(app_main, db, "nurse@scale-test.aivana", "Nurse", org_id)
        return {"doctor": doctor, "nursing_station": nursing_station, "head_nurse": head_nurse, "nurse": nurse}
    finally:
        db.close()


def _auth_headers(user):
    from tests._voice_helpers import mint_tokens
    tokens = mint_tokens(user)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _new_page(context):
    from tests._voice_helpers import MOCK_MEDIA_RECORDER_INIT_SCRIPT

    page = context.new_page()
    page.add_init_script(MOCK_MEDIA_RECORDER_INIT_SCRIPT)
    page.on("dialog", lambda d: d.accept())
    js_errors = []
    page.on("pageerror", lambda exc: js_errors.append(str(exc)))
    page.js_errors = js_errors
    return page


def _backdate_admission(app_main, patient_id, day):
    from app.models import Patient

    db = app_main.SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if patient:
            patient.admission_date = datetime.utcnow() - timedelta(days=max(day - 1, 0))
            db.commit()
    finally:
        db.close()


def _drive_opd_consult(context, base_url, app_main, doctor, patient_id, utterances):
    from tests._voice_helpers import mint_tokens, set_tokens_in_browser

    out = {"js_errors": [], "tasks_created": 0, "interaction_warnings": False, "error": None, "prescription": None}
    page = _new_page(context)
    try:
        tokens = mint_tokens(doctor)
        set_tokens_in_browser(page, base_url, tokens["access_token"], tokens["refresh_token"])
        page.goto(f"{base_url}/opd.html")
        page.wait_for_function("document.querySelector('#patient-select').options.length > 1", timeout=20000)
        page.select_option("#patient-select", str(patient_id))
        full_text = " ".join(u for u in utterances if u).strip()
        # Not routed through real Groq Whisper -- see module docstring. Reassigned fresh per
        # visit (safe: run_scenario drives visits strictly sequentially, never concurrently).
        app_main.scribe.transcribe_audio = lambda audio_bytes, content_type, filename, _t=full_text: _t
        page.click("#start-consult-btn")
        page.wait_for_timeout(120)
        page.click("#stop-consult-btn")
        if len(full_text) < 10:
            # One (mocked, cost-free) /api/transcribe-audio round trip now happens even for a
            # short transcript before the frontend's own length guard can react to it (the
            # guard runs on the RETURNED transcript, not before the recording upload) -- allow
            # a bit more time than the pre-MediaRecorder version needed for that extra hop.
            page.wait_for_timeout(600)
            status = page.eval_on_selector("#analysis-status", "el => el.textContent") or ""
            if "too short" not in status.lower():
                out["error"] = f"expected short-transcript guard, got: {status!r}"
            return out
        page.wait_for_function(
            "document.querySelector('#analysis-status').textContent.includes('ready') || "
            "document.querySelector('#analysis-status').textContent.includes('Error')",
            timeout=45000,
        )
        pre_status = page.eval_on_selector("#analysis-status", "el => el.textContent") or ""
        if "Error" in pre_status:
            out["error"] = f"scribe call failed: {pre_status}"
            return out
        # Wizard navigation: Clinical Note -> Interactions -> Prescription, where Finalize lives.
        page.click("#continue-to-interactions-btn")
        page.click("#continue-to-prescription-btn")
        page.click("#finalize-btn")
        # Finalize triggers a REAL server-side drug-interaction LLM call (reasoning tokens
        # included even with reasoning_format=hidden) before it updates the status text --
        # a fixed short sleep here previously raced ahead of that call finishing and read a
        # stale/empty #interaction-results, undercounting real interaction-warning hits.
        page.wait_for_function(
            "document.querySelector('#analysis-status').textContent.includes('Finalized') || "
            "document.querySelector('#analysis-status').textContent.includes('Error')",
            timeout=60000,
        )
        status_text = page.eval_on_selector("#analysis-status", "el => el.textContent") or ""
        m = re.search(r"(\d+) task", status_text)
        out["tasks_created"] = int(m.group(1)) if m else 0
        interaction_text = page.eval_on_selector("#interaction-results", "el => el.textContent") or ""
        out["interaction_warnings"] = "Severity:" in interaction_text
        # The complete finalized prescription -- what the doctor actually reviewed and saved,
        # not just counts derived from it. Reads the real draft fields + the same
        # getMedications()/getLabTests() the app itself uses to build the save payload.
        out["prescription"] = page.evaluate("""() => ({
            chiefComplaint: document.getElementById('chief-complaint').value,
            hpi: document.getElementById('hpi').value,
            primaryDiagnosis: document.getElementById('primary-diagnosis').value,
            differentialDiagnosis: document.getElementById('differential-diagnosis').value,
            advice: document.getElementById('advice').value,
            medications: typeof getMedications === 'function' ? getMedications() : [],
            labTests: typeof getLabTests === 'function' ? getLabTests() : [],
        })""")
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        out["js_errors"] = list(page.js_errors)
        page.close()
    return out


def _drive_ipd_round(context, base_url, app_main, doctor, patient_id, utterances):
    from tests._voice_helpers import mint_tokens, set_tokens_in_browser

    out = {"js_errors": [], "tasks_created": 0, "interaction_warnings": False, "error": None, "prescription": None}
    page = _new_page(context)
    try:
        tokens = mint_tokens(doctor)
        set_tokens_in_browser(page, base_url, tokens["access_token"], tokens["refresh_token"])
        page.goto(f"{base_url}/ipd.html")
        page.wait_for_function("document.querySelectorAll('.patient-card').length > 0", timeout=20000)
        page.evaluate("(id) => openWardRound(id)", patient_id)
        page.wait_for_selector("#ward-round-modal[style*='flex']", timeout=15000)
        full_text = " ".join(u for u in utterances if u).strip()
        # Not routed through real Groq Whisper -- see module docstring. Reassigned fresh per
        # visit (safe: run_scenario drives visits strictly sequentially, never concurrently).
        app_main.scribe.transcribe_audio = lambda audio_bytes, content_type, filename, _t=full_text: _t
        page.click("#round-start-btn")
        page.wait_for_timeout(120)
        page.click("#round-stop-btn")
        if len(full_text) < 10:
            # See the analogous comment in _drive_opd_consult -- one mocked /transcribe-audio
            # round trip now happens before the guard can react.
            page.wait_for_timeout(600)
            status = page.eval_on_selector("#round-status", "el => el.textContent") or ""
            if "too short" not in status.lower():
                out["error"] = f"expected short-transcript guard, got: {status!r}"
            return out
        page.wait_for_function(
            "document.querySelector('#round-finalize-btn').style.display === 'inline-block' || "
            "document.querySelector('#round-status').textContent.includes('Error')",
            timeout=45000,
        )
        pre_status = page.eval_on_selector("#round-status", "el => el.textContent") or ""
        if "Error" in pre_status:
            out["error"] = f"round call failed: {pre_status}"
            return out
        page.click("#round-finalize-btn")
        # Same real-LLM-call race as the OPD flow -- wait for the actual completion signal.
        page.wait_for_function(
            "document.querySelector('#round-status').textContent.includes('Finalized') || "
            "document.querySelector('#round-status').textContent.includes('Error')",
            timeout=60000,
        )
        status_text = page.eval_on_selector("#round-status", "el => el.textContent") or ""
        m = re.search(r"(\d+) task", status_text)
        out["tasks_created"] = int(m.group(1)) if m else 0
        interaction_text = page.eval_on_selector("#round-interaction-results", "el => el.textContent") or ""
        out["interaction_warnings"] = "Severity:" in interaction_text
        out["prescription"] = page.evaluate("""() => ({
            chiefComplaint: document.getElementById('round-chief-complaint').value,
            hpi: document.getElementById('round-hpi').value,
            primaryDiagnosis: document.getElementById('round-diagnosis').value,
            differentialDiagnosis: document.getElementById('round-differential').value,
            advice: document.getElementById('round-advice').value,
            medications: typeof getRoundMedications === 'function' ? getRoundMedications() : [],
            labTests: typeof getRoundLabs === 'function' ? getRoundLabs() : [],
            admissionDay: document.getElementById('round-day').textContent,
        })""")
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        out["js_errors"] = list(page.js_errors)
        page.close()
    return out


def _drive_nurse_task_completion(context, base_url, nurse):
    from tests._voice_helpers import mint_tokens, set_tokens_in_browser

    out = {"js_errors": [], "error": None}
    page = _new_page(context)
    try:
        tokens = mint_tokens(nurse)
        set_tokens_in_browser(page, base_url, tokens["access_token"], tokens["refresh_token"])
        page.goto(f"{base_url}/ipd.html")
        page.click("#tasks-nav-btn")
        page.wait_for_function("document.querySelectorAll('#task-list > div').length > 0", timeout=15000)
        btn = page.query_selector("#task-list button")
        if btn:
            btn.click()
            page.wait_for_timeout(500)
        else:
            out["error"] = "no completable task visible in nurse task list"
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        out["js_errors"] = list(page.js_errors)
        page.close()
    return out


def _fire_concurrent_task_race(base_url, nurse_headers, hn_headers, patient_id):
    """EDGE sub-type: two near-simultaneous completions of the same task shouldn't crash the
    server or leave inconsistent state -- exercises PATCH /api/ipd/tasks/{id} under a real race."""
    import requests

    r = requests.get(f"{base_url}/api/ipd/tasks/{patient_id}", headers=hn_headers, timeout=15)
    if not r.ok or not r.json():
        return {"error": "no task available for race test"}
    task_id = r.json()[0]["id"]

    results = []

    def _complete():
        try:
            resp = requests.patch(
                f"{base_url}/api/ipd/tasks/{task_id}", headers=nurse_headers,
                json={"status": "Completed"}, timeout=15,
            )
            results.append(resp.status_code)
        except Exception as exc:
            results.append(str(exc))

    threads = [threading.Thread(target=_complete) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    if any(isinstance(r, int) and r >= 500 for r in results):
        return {"error": f"concurrent completion produced a server error: {results}"}
    return {"error": None}


def run_scenario(scenario, ctx):
    import requests

    result = {
        "test_id": scenario.test_id, "category": scenario.category,
        "specialty": scenario.specialty, "language": scenario.language,
        "age": scenario.age, "age_band": scenario.age_band, "gender": scenario.gender,
        "admission_days": scenario.admission_days, "med_complexity": scenario.med_complexity,
        "interacting_pair": list(scenario.interacting_pair) if scenario.interacting_pair else None,
        "edge_type": scenario.edge_type, "status": "pass", "error": None, "notes": [],
        "tasks_created_total": 0, "interaction_warnings_triggered": False, "js_errors": [],
        "prescriptions": [],  # one entry per visit/round -- the actual finalized clinical output
        "started_at": datetime.utcnow().isoformat(),
    }
    t0 = time.monotonic()
    try:
        base_url = ctx["base_url"]
        users = ctx["users"]
        context = ctx["context"]
        req_bucket = ctx["req_bucket"]
        token_bucket = ctx["token_bucket"]
        app_main = ctx["app_main"]
        # Minted fresh per scenario, not once at process startup: access tokens expire after
        # ACCESS_TOKEN_EXPIRE_MINUTES (15 min by default) -- reusing headers minted once at
        # the start of a run that's expected to take hours meant every REST call after the
        # first ~15 minutes failed with 401, which is exactly what happened the first time
        # this ran (38 passes in the first ~15 min, then 462 straight 401 failures).
        ns_headers = _auth_headers(users["nursing_station"])
        hn_headers = _auth_headers(users["head_nurse"])
        nurse_headers = _auth_headers(users["nurse"])

        ward = "OPD Walk-in" if scenario.admission_days == 0 else "General Ward"
        r = requests.post(f"{base_url}/api/ipd/patients", headers=ns_headers, json={
            "name": f"Test Patient {scenario.test_id}", "age": scenario.age,
            "gender": scenario.gender, "ward": ward, "bed": f"T-{scenario.test_id}", "diagnosis": "",
        }, timeout=15)
        r.raise_for_status()
        patient_id = r.json()["id"]

        requests.post(
            f"{base_url}/api/ipd/assign", headers=hn_headers,
            json={"patient_id": patient_id, "nurse_id": users["nurse"].id}, timeout=15,
        ).raise_for_status()

        total_tasks = 0
        interaction_triggered = False
        expected_visits = 0   # visits with a real (>=10 char) transcript -- a prescription is
        failed_visits = 0     # actually expected from these, unlike the short-transcript guards

        for i, utterances in enumerate(scenario.visits):
            day = scenario.round_days[i] if i < len(scenario.round_days) else 1
            full_text_len = len(" ".join(utterances))
            # Only a >=10-char transcript actually reaches the backend (the frontend itself
            # blocks shorter ones client-side, see the short-transcript-guard edge cases) --
            # don't spend request/token budget pacing for a call that will never happen.
            if full_text_len >= 10:
                expected_visits += 1
                # A single visit makes THREE real Groq calls, not two -- verified against
                # main.py directly: scribe_transcript (extraction) + check_drug_interactions
                # called from creation (POST /api/scribe or /api/ipd/rounds, OPD's frontend
                # also fires its own /api/drug-interactions here) + check_drug_interactions
                # called AGAIN from PATCH /api/consultations/{id}/finalize against the full
                # active regimen. Under-pacing for only 2 was the real reason 429s persisted
                # even after fixing the per-token rate -- the request COUNT budget was also
                # being drawn down faster than modeled.
                req_bucket.consume(1)       # extraction call, always made
                req_bucket.consume(1)       # interaction check at creation time
                req_bucket.consume(1)       # interaction check again at finalize time
                token_bucket.consume(ESTIMATED_TOKENS["extraction"])
                token_bucket.consume(ESTIMATED_TOKENS["interaction"])
                token_bucket.consume(ESTIMATED_TOKENS["interaction"])

            if scenario.admission_days > 0:
                _backdate_admission(app_main, patient_id, day)
                outcome = _drive_ipd_round(context, base_url, app_main, users["doctor"], patient_id, utterances)
            else:
                outcome = _drive_opd_consult(context, base_url, app_main, users["doctor"], patient_id, utterances)

            result["js_errors"].extend(outcome.get("js_errors", []))
            total_tasks += outcome.get("tasks_created", 0)
            interaction_triggered = interaction_triggered or outcome.get("interaction_warnings", False)
            if outcome.get("prescription"):
                result["prescriptions"].append({"visit": i + 1, "day": day, **outcome["prescription"]})
            if outcome.get("error"):
                result["notes"].append(f"visit {i + 1}: {outcome['error']}")
                # A visit that had a real transcript but errored (timeout, scribe failure, etc.)
                # is a genuine failure of the thing under test -- it used to only land in
                # `notes` while `status` silently stayed "pass", so a case where EVERY visit
                # timed out and captured zero prescription content was still counted as a pass.
                if full_text_len >= 10:
                    failed_visits += 1

        result["tasks_created_total"] = total_tasks
        result["interaction_warnings_triggered"] = interaction_triggered

        if total_tasks > 0:
            nurse_outcome = _drive_nurse_task_completion(context, base_url, users["nurse"])
            result["js_errors"].extend(nurse_outcome.get("js_errors", []))
            if nurse_outcome.get("error"):
                result["notes"].append(f"nurse: {nurse_outcome['error']}")

        if scenario.edge_type == "concurrent_task_race" and total_tasks > 0:
            race = _fire_concurrent_task_race(base_url, nurse_headers, hn_headers, patient_id)
            if race.get("error"):
                result["notes"].append(f"race: {race['error']}")
                result["status"] = "fail"
                result["error"] = race["error"]

        if result["status"] == "pass":
            if result["js_errors"]:
                result["status"] = "fail"
                result["error"] = f"JS errors: {result['js_errors'][:3]}"
            elif expected_visits > 0 and failed_visits >= expected_visits:
                result["status"] = "fail"
                result["error"] = f"all {expected_visits} visit(s) with a real transcript failed to produce a prescription"
            elif expected_visits > 0 and failed_visits > 0:
                # Partial failure in a multi-round case (some rounds succeeded, at least one
                # didn't) -- worth surfacing as a failure too rather than only a note, since
                # "3 of 5 rounds captured" is a real defect even if it's not total failure.
                result["status"] = "fail"
                result["error"] = f"{failed_visits} of {expected_visits} visit(s) failed to produce a prescription"
            elif scenario.edge_type == "interacting_pair" and not interaction_triggered:
                result["status"] = "fail"
                result["error"] = "expected an interaction warning for a known interacting pair; none recorded"

    except Exception as exc:
        result["status"] = "fail"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()[-2000:]

    result["duration_sec"] = round(time.monotonic() - t0, 2)
    result["finished_at"] = datetime.utcnow().isoformat()
    return result


def load_completed_ids():
    if not RESULTS_PATH.exists():
        return set()
    ids = set()
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ids.add(json.loads(line)["test_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return ids


def append_result(result):
    with open(RESULTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--categories", default=None, help="Comma-separated category subset, e.g. OPD,EDGE")
    parser.add_argument("--smoke", type=int, default=None, help="Run only N cases per category (validation run)")
    parser.add_argument("--total-cases", type=int, default=None,
                         help="Proportionally scale the full category mix down (or up) to this total")
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing results.jsonl and rerun everything")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--rate-tokens-per-sec", type=float, default=75.0,
                         help="Fallback only, used if the live limits probe fails; 75/sec = 4500 TPM, safely under llama-3.1-8b-instant's 6000 TPM")
    parser.add_argument("--rate-requests-per-sec", type=float, default=1.0 / 6.0,
                         help="Real binding constraint on the configured Groq key; see RequestBucket docstring")
    # Deliberately small, NOT the full remaining daily quota: a token-bucket's capacity is
    # its BURST allowance -- how much can be spent instantly before throttling kicks in.
    # Setting it to the full ~14,000 remaining requests (what "capacity" originally meant
    # here) let 3 real calls per visit fire back-to-back with zero enforced spacing for
    # hundreds of cases straight, since the bucket never drained close to empty. 429s kept
    # recurring through two rounds of "fix the rate" precisely because the rate was never
    # actually being enforced -- only the rarely-hit capacity ceiling was. A small capacity
    # forces the bucket to genuinely throttle at the sustained rate almost immediately.
    parser.add_argument("--request-budget-capacity", type=float, default=8.0)
    # Must comfortably cover ONE visit's own total draw (extraction ~2200 + 2x interaction
    # ~1200 = ~4600, see ESTIMATED_TOKENS) -- verified live, setting this to 2000 (smaller
    # than a single visit's need) meant EVERY visit cascaded through multiple large forced
    # sleeps back-to-back (~35s of pure pacing before any browser work even started), which
    # looked identical to a hang from the outside (11 minutes, zero new results). The point
    # of a small capacity is to stop bursting ACROSS visits, not to fragment a single visit's
    # own necessary calls into artificial waits.
    parser.add_argument("--token-budget-capacity", type=float, default=5000.0)
    args = parser.parse_args()

    app_main = _bootstrap_app()
    from tests._voice_helpers import start_live_server
    from tests.scale.scenario_generator import CATEGORY_COUNTS, generate_scenario, scale_counts

    counts = dict(CATEGORY_COUNTS)
    if args.total_cases:
        counts = scale_counts(args.total_cases)
    if args.categories:
        selected = set(c.strip().upper() for c in args.categories.split(","))
        counts = {k: v for k, v in counts.items() if k in selected}
    if args.smoke:
        counts = {k: min(v, args.smoke) for k, v in counts.items()}

    completed = set() if args.no_resume else load_completed_ids()
    print(f"Resuming with {len(completed)} already-completed test_ids skipped." if completed else "Starting fresh run.")

    base_url, stop_server = start_live_server(app_main.app)
    print(f"Live server up at {base_url}")
    users = setup_users(app_main)
    # Auth headers are minted fresh per-scenario inside run_scenario (see the comment there)
    # rather than once here -- a run spanning hours can't reuse one set of 15-minute tokens.

    from playwright.sync_api import sync_playwright

    total = sum(counts.values())
    done_count = 0
    pass_count = 0
    fail_count = 0
    t_start = time.monotonic()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(permissions=["microphone"])
        probed = _probe_groq_limits()
        if probed:
            print(
                f"Probed real Groq limits: {probed['starting_requests']} requests remaining, "
                f"{probed['token_rate_per_sec']:.1f} tokens/sec sustained "
                f"(capacity {probed['token_capacity']:.0f})"
            )
        # capacity is deliberately the small --*-budget-capacity value, NOT the large probed
        # daily/per-minute totals -- see the --request-budget-capacity help text for why. The
        # probe still sets the *rate* (how fast the bucket refills) and an informational
        # starting-tokens value, but starting_tokens is clamped to `capacity` regardless (see
        # RequestBucket.__init__), so this can't accidentally start the bucket "full" at a
        # burst-sized capacity.
        req_bucket = RequestBucket(
            rate_per_sec=args.rate_requests_per_sec, capacity=args.request_budget_capacity,
            starting_tokens=args.request_budget_capacity,
        )
        token_bucket = TokenBucket(
            rate_per_sec=probed["token_rate_per_sec"] if probed else args.rate_tokens_per_sec,
            capacity=args.token_budget_capacity,
        )
        ctx = {
            "base_url": base_url, "users": users, "context": context,
            "req_bucket": req_bucket, "token_bucket": token_bucket, "app_main": app_main,
        }

        try:
            for category, n in counts.items():
                for seq in range(1, n + 1):
                    test_id = f"{category}-{seq:05d}"
                    if test_id in completed:
                        continue
                    scenario = generate_scenario(category, seq)
                    result = run_scenario(scenario, ctx)
                    append_result(result)
                    done_count += 1
                    if result["status"] == "pass":
                        pass_count += 1
                    else:
                        fail_count += 1
                    if done_count % 5 == 0 or done_count == total:
                        elapsed = time.monotonic() - t_start
                        rate = done_count / elapsed if elapsed > 0 else 0
                        print(
                            f"[{done_count}/{total - len(completed)} this run] "
                            f"pass={pass_count} fail={fail_count} "
                            f"({rate:.2f}/sec, {elapsed/60:.1f} min elapsed) "
                            f"req_budget~{req_bucket.tokens:.0f} "
                            f"last={test_id}:{result['status']}"
                        )
        finally:
            context.close()
            browser.close()

    stop_server()
    print(f"Done. {pass_count} passed, {fail_count} failed, {done_count} run this session.")
    print(f"Results appended to {RESULTS_PATH}")


if __name__ == "__main__":
    main()

"""
Drives every curated use case in tests/scenarios/curated_use_cases.py through the REAL
voice-simulated pipeline (mic -> speech -> Process/Stop Consulting -> AI extraction -> saved
record), against a real live local server, and saves the resulting artifacts to
"final test output/<use_case_id>/" at the repo root -- exactly matching how a doctor/nurse
actually uses this system, not a raw API shortcut.

AI source: this script always attempts a real Groq API call first (one lightweight probe at
collection time). If a live key is available, every case runs through the real model -- real
cost, real latency, real extraction quality, exactly as requested. If the configured key is
invalid/unavailable, it falls back to this file's curated `synthetic_extraction` /
`synthetic_discharge` content (clinically-plausible stand-ins authored alongside each
transcript) so the full pipeline still gets exercised end-to-end and real output artifacts are
still produced -- each one's metadata.json says exactly which path was used, so nothing is
presented as real AI output when it isn't. Re-run this file after fixing the API key to
regenerate every case with real model output.
"""
import json
import os
import re
import time

import pytest
import requests

from tests.e2e.conftest import fire_speech_result, mint_tokens, set_tokens_in_browser
from tests.scenarios.curated_use_cases import IPD_USE_CASES, OPD_USE_CASES

pytestmark = pytest.mark.e2e

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUTPUT_ROOT = os.path.join(REPO_ROOT, "final test output")


def _probe_live_groq() -> bool:
    try:
        import sys
        sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))
        from app.config import settings
        if not settings.GROQ_API_KEY:
            return False
        headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": settings.GROQ_MODEL, "messages": [{"role": "user", "content": "Reply with exactly: OK"}], "max_tokens": 5}
        resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        return resp.status_code == 200
    except Exception:
        return False


LIVE_GROQ_AVAILABLE = _probe_live_groq()


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text or "")


def _chunk_transcript(transcript: str, n: int = 4):
    """Split a transcript into a few pieces to simulate natural multi-utterance speech
    (a real consultation is spoken in turns, not delivered as one giant blob)."""
    sentences = re.split(r"(?<=[।.!?॥])\s+", transcript.strip())
    sentences = [s for s in sentences if s]
    if len(sentences) <= n:
        return sentences or [transcript]
    chunk_size = max(1, len(sentences) // n)
    return [" ".join(sentences[i:i + chunk_size]) for i in range(0, len(sentences), chunk_size)]


# ---------------------------------------------------------------------------
# OPD use cases: real voice-simulated "Start Consultation -> speak -> Stop" flow.
# ---------------------------------------------------------------------------

@pytest.fixture
def opd_doctor_and_patient(make_user, db_session):
    from app.models import Patient

    def _make(use_case_id):
        doctor = make_user(email=f"doc-{use_case_id}@scenarios.com", role="Doctor")
        patient = Patient(name=f"Patient for {use_case_id}", ward="OPD",
                           organization_id=doctor.organization_id, created_by=doctor.id)
        db_session.add(patient)
        db_session.commit()
        db_session.refresh(patient)
        return doctor, patient
    return _make


@pytest.mark.parametrize("case", OPD_USE_CASES, ids=[c["id"] for c in OPD_USE_CASES])
def test_generate_opd_output(js_page, live_server_url, opd_doctor_and_patient, monkeypatch, case):
    import app.main as app_main

    doctor, patient = opd_doctor_and_patient(case["id"])

    ai_source = "live_groq" if LIVE_GROQ_AVAILABLE else "synthetic_fallback"
    if not LIVE_GROQ_AVAILABLE:
        raw = json.dumps(case["synthetic_extraction"])
        monkeypatch.setattr(app_main.scribe, "_call_groq_api", lambda *a, **k: raw)

    tokens = mint_tokens(doctor)
    set_tokens_in_browser(js_page, live_server_url, tokens["access_token"], tokens["refresh_token"])
    js_page.goto(f"{live_server_url}/opd.html")
    js_page.wait_for_selector("#patient-select")
    js_page.wait_for_function("document.querySelector('#patient-select').options.length > 1")
    js_page.select_option("#patient-select", str(patient.id))

    js_page.click("#start-consult-btn")
    js_page.wait_for_timeout(150)
    for chunk in _chunk_transcript(case["transcript"]):
        fire_speech_result(js_page, chunk)
        js_page.wait_for_timeout(80)
    js_page.click("#stop-consult-btn")
    js_page.wait_for_timeout(1500 if LIVE_GROQ_AVAILABLE else 800)

    assert js_page.js_errors == [], f"{case['id']}: unexpected JS errors {js_page.js_errors}"

    draft = {
        "chiefComplaint": js_page.eval_on_selector("#chief-complaint", "el => el.value"),
        "hpi": js_page.eval_on_selector("#hpi", "el => el.value"),
        "primaryDiagnosis": js_page.eval_on_selector("#primary-diagnosis", "el => el.value"),
        "differentialDiagnosis": js_page.eval_on_selector("#differential-diagnosis", "el => el.value"),
        "advice": js_page.eval_on_selector("#advice", "el => el.value"),
    }

    out_dir = os.path.join(OUTPUT_ROOT, case["id"])
    _write_text(os.path.join(out_dir, "transcript.txt"), case["transcript"])
    _write_json(os.path.join(out_dir, "prescription_output.json"), draft)
    _write_json(os.path.join(out_dir, "metadata.json"), {
        "use_case_id": case["id"], "type": "OPD", "setting": case["setting"], "specialty": case["specialty"],
        "language": case["language"], "duration_label": case["duration_label"], "scale": case["scale"],
        "ai_source": ai_source, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })

    assert draft["chiefComplaint"] or draft["primaryDiagnosis"], f"{case['id']}: draft came back empty"


# ---------------------------------------------------------------------------
# IPD use cases: admission -> per-day voice-simulated nursing note + structured vitals ->
# discharge summary, driven through the real IPD UI.
# ---------------------------------------------------------------------------

@pytest.fixture
def ipd_ward_setup(make_user):
    def _make(use_case_id):
        head_nurse = make_user(email=f"head-{use_case_id}@scenarios.com", role="HeadNurse")
        nurse = make_user(email=f"nurse-{use_case_id}@scenarios.com", role="Nurse", organization_id=head_nurse.organization_id)
        return head_nurse, nurse
    return _make


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.mark.parametrize("case", IPD_USE_CASES, ids=[c["id"] for c in IPD_USE_CASES])
def test_generate_ipd_output(js_page, live_server_url, ipd_ward_setup, monkeypatch, case):
    import app.main as app_main

    head_nurse, nurse = ipd_ward_setup(case["id"])
    hn_token = mint_tokens(head_nurse)["access_token"]
    nurse_token = mint_tokens(nurse)["access_token"]

    admit_resp = requests.post(f"{live_server_url}/api/ipd/patients",
                                json={"name": f"Patient for {case['id']}", "ward": case["ward"], "diagnosis": case["admission_diagnosis"]},
                                headers=_auth_headers(hn_token), timeout=15)
    patient_id = admit_resp.json()["id"]
    requests.post(f"{live_server_url}/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse.id},
                  headers=_auth_headers(hn_token), timeout=15)

    ai_source = "live_groq" if LIVE_GROQ_AVAILABLE else "synthetic_fallback"

    tokens = mint_tokens(nurse)
    set_tokens_in_browser(js_page, live_server_url, tokens["access_token"], tokens["refresh_token"])
    js_page.goto(f"{live_server_url}/ipd.html")
    js_page.wait_for_timeout(300)

    daily_notes_out = []
    for day_entry in case["stay_notes"]:
        # Structured vitals recorded directly (already extensively covered by the dedicated
        # voice-vitals test suites) -- what this script focuses on capturing is the real
        # voice-driven nursing note in the target language.
        requests.post(f"{live_server_url}/api/ipd/vitals", json={"patient_id": patient_id, **day_entry["vitals"]},
                      headers=_auth_headers(nurse_token), timeout=15)

        note_field = next(k for k in day_entry if k.startswith("note_") and day_entry[k])
        note_text = day_entry[note_field]

        if not LIVE_GROQ_AVAILABLE:
            raw = json.dumps({"subjective": note_text, "objective": "", "assessment": "", "plan": ""})
            monkeypatch.setattr(app_main.scribe, "_call_groq_api", lambda *a, **k: raw)

        js_page.evaluate(f"openNursingConsult({patient_id})")
        js_page.wait_for_timeout(150)
        js_page.click("#nursing-voice-btn", force=True)
        js_page.wait_for_timeout(80)
        for chunk in _chunk_transcript(note_text, n=2):
            fire_speech_result(js_page, chunk)
            js_page.wait_for_timeout(80)
        js_page.click("#nursing-process-btn")
        js_page.wait_for_timeout(1200 if LIVE_GROQ_AVAILABLE else 600)

        js_page.on("dialog", lambda d: d.accept())
        js_page.click("#nursing-save-btn")
        js_page.wait_for_timeout(500)
        # ipd.html's save handler already closes the modal itself on success
        # (alert -> closeModal('nursing-consult-modal')) -- no explicit close needed here.

        daily_notes_out.append({"day": day_entry["day"], "voice_text": note_text, "vitals": day_entry["vitals"]})

    assert js_page.js_errors == [], f"{case['id']}: unexpected JS errors {js_page.js_errors}"

    if not LIVE_GROQ_AVAILABLE:
        raw = json.dumps(case["synthetic_discharge"])
        monkeypatch.setattr(app_main.scribe, "_call_groq_api", lambda *a, **k: raw)

    summary_resp = requests.post(f"{live_server_url}/api/ipd/patients/{patient_id}/discharge-summary",
                                  headers=_auth_headers(hn_token), timeout=30)
    assert summary_resp.status_code == 200, f"{case['id']}: discharge summary generation failed: {summary_resp.text}"
    discharge_summary = summary_resp.json()

    requests.put(f"{live_server_url}/api/patients/{patient_id}", json={"status": "Discharged"}, headers=_auth_headers(hn_token), timeout=15)

    out_dir = os.path.join(OUTPUT_ROOT, case["id"])
    _write_json(os.path.join(out_dir, "admission_info.json"), {
        "patient_id": patient_id, "ward": case["ward"], "admission_diagnosis": case["admission_diagnosis"],
    })
    for day_data in daily_notes_out:
        _write_text(os.path.join(out_dir, "daily_notes", f"day_{day_data['day']}_note.txt"), day_data["voice_text"])
        _write_json(os.path.join(out_dir, "daily_notes", f"day_{day_data['day']}_vitals.json"), day_data["vitals"])
    _write_json(os.path.join(out_dir, "discharge_summary.json"), discharge_summary)
    _write_json(os.path.join(out_dir, "metadata.json"), {
        "use_case_id": case["id"], "type": "IPD", "setting": case["setting"], "specialty": case["specialty"],
        "language": case["language"], "scale": case["scale"], "ward": case["ward"],
        "ai_source": ai_source, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })

    assert discharge_summary["discharge_diagnosis"], f"{case['id']}: discharge summary came back empty"


def test_write_output_index(request):
    """Runs last (by pytest's default file+definition ordering within this module, after all
    parametrized generation tests) and writes a top-level index of every use case and whether
    it used real or synthetic AI content, so the folder is self-documenting."""
    all_cases = OPD_USE_CASES + IPD_USE_CASES
    index = {
        "total_use_cases": len(all_cases),
        "opd_cases": len(OPD_USE_CASES),
        "ipd_cases": len(IPD_USE_CASES),
        "ai_source": "live_groq" if LIVE_GROQ_AVAILABLE else "synthetic_fallback",
        "note": (
            "Generated with real Groq API calls." if LIVE_GROQ_AVAILABLE else
            "Groq API key was invalid/unavailable when this was generated, so structured "
            "output (prescriptions/discharge summaries) uses this repo's curated synthetic "
            "content instead of live model output -- the full pipeline (voice input, storage, "
            "retrieval) was still exercised for real. Fix backend/.env's GROQ_API_KEY and "
            "re-run `pytest tests/scenarios -m e2e` to regenerate every case with real AI output."
        ),
        "languages_covered": sorted({c["language"] for c in all_cases}),
        "use_case_ids": [c["id"] for c in all_cases],
    }
    _write_json(os.path.join(OUTPUT_ROOT, "_index.json"), index)

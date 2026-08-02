"""
Real-browser regression tests for the OPD "Start Consulting -> speak -> Stop Consulting"
flow (frontend/opd.html). These caught two real production bugs during manual investigation
of a bug report ("data not getting filled in after Stop Consulting"):

  1. opd.html's apiRequest() declared `const accessToken` but reassigned it after a token
     refresh -- a guaranteed `TypeError: Assignment to constant variable` on the very first
     API call made after the 15-minute access token expires, silently killing the request
     that would have saved/displayed the consultation. A real consultation (see the multi-page
     transcripts in tests/from_data/fixtures.py) very plausibly outlasts 15 minutes.
  2. The live transcript accumulator kept two variables (`accumulatedTranscript`,
     `currentFinal`) that were always incremented identically and then concatenated together
     for display/submission -- doubling every "final" chunk of speech in what actually got
     sent to the AI scribe.

Both are fixed in opd.html; these tests pin the fix down so neither regresses.
"""
import pytest

from tests.e2e.conftest import (
    fire_speech_result,
    mint_expired_access_token,
    mint_tokens,
    set_tokens_in_browser,
)

pytestmark = pytest.mark.e2e


@pytest.fixture
def opd_patient(make_user, db_session):
    from app.models import Patient

    doctor = make_user(email="doctor@e2e-opd.com", role="Doctor")
    patient = Patient(name="E2E OPD Patient", age=30, gender="M", ward="OPD",
                       organization_id=doctor.organization_id, created_by=doctor.id)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    return doctor, patient


def _start_speak_stop(js_page, live_server_url, patient_id, utterances):
    js_page.goto(f"{live_server_url}/opd.html")
    js_page.wait_for_selector("#patient-select")
    js_page.wait_for_function("document.querySelector('#patient-select').options.length > 1")
    js_page.select_option("#patient-select", str(patient_id))
    js_page.click("#start-consult-btn")
    js_page.wait_for_timeout(150)
    for text in utterances:
        fire_speech_result(js_page, text)
        js_page.wait_for_timeout(100)
    transcript_before_stop = js_page.eval_on_selector("#transcript-input", "el => el.value")
    js_page.click("#stop-consult-btn")
    js_page.wait_for_timeout(1200)
    return transcript_before_stop


def test_voice_consultation_populates_draft_with_fresh_token(
    js_page, live_server_url, opd_patient, monkeypatch
):
    import app.main as app_main
    doctor, patient = opd_patient
    monkeypatch.setattr(app_main.scribe, "_call_groq_api",
                         lambda *a, **k: '{"chiefComplaint": "Fever and cough"}')

    tokens = mint_tokens(doctor)
    set_tokens_in_browser(js_page, live_server_url, tokens["access_token"], tokens["refresh_token"])

    _start_speak_stop(js_page, live_server_url, patient.id,
                       ["Doctor: patient reports fever and cough for three days"])

    assert js_page.js_errors == [], f"unexpected JS errors: {js_page.js_errors}"
    chief_complaint = js_page.eval_on_selector("#chief-complaint", "el => el.value")
    assert chief_complaint == "Fever and cough"


def test_voice_consultation_survives_access_token_expiring_mid_session(
    js_page, live_server_url, opd_patient, monkeypatch
):
    """
    Regression test for the `const accessToken` crash: mints a token that's already expired,
    so apiRequest()'s very first call (loading the patient dropdown) must hit the 401 ->
    refresh path. Before the fix this threw `TypeError: Assignment to constant variable` and
    the patient dropdown never populated, let alone the consultation draft.
    """
    import app.main as app_main
    doctor, patient = opd_patient
    monkeypatch.setattr(app_main.scribe, "_call_groq_api",
                         lambda *a, **k: '{"chiefComplaint": "Fever and cough"}')

    tokens = mint_tokens(doctor)
    expired_access = mint_expired_access_token(doctor)
    set_tokens_in_browser(js_page, live_server_url, expired_access, tokens["refresh_token"])

    _start_speak_stop(js_page, live_server_url, patient.id,
                       ["Doctor: patient reports fever and cough for three days"])

    assert js_page.js_errors == [], (
        f"apiRequest crashed on token refresh: {js_page.js_errors}"
    )
    chief_complaint = js_page.eval_on_selector("#chief-complaint", "el => el.value")
    assert chief_complaint == "Fever and cough", (
        "draft was not populated after an access-token refresh mid-session"
    )


def test_transcript_is_not_duplicated_across_multiple_speech_results(
    js_page, live_server_url, opd_patient, monkeypatch
):
    """Regression test for the accumulatedTranscript/currentFinal double-counting bug."""
    import app.main as app_main
    doctor, patient = opd_patient
    captured_prompts = []

    def _capture(prompt, system=None, temperature=0.3):
        captured_prompts.append(prompt)
        return '{"chiefComplaint": "test"}'

    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _capture)

    tokens = mint_tokens(doctor)
    set_tokens_in_browser(js_page, live_server_url, tokens["access_token"], tokens["refresh_token"])

    transcript_before_stop = _start_speak_stop(
        js_page, live_server_url, patient.id,
        ["Doctor: first thing said", "Patient: second thing said"],
    )

    assert transcript_before_stop.count("first thing said") == 1, (
        f"transcript duplicated: {transcript_before_stop!r}"
    )
    assert transcript_before_stop.count("second thing said") == 1, (
        f"transcript duplicated: {transcript_before_stop!r}"
    )
    assert captured_prompts, "scribe was never called"
    assert captured_prompts[0].count("first thing said") == 1

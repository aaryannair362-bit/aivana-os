"""
Real-browser coverage of the nurse-facing voice mic UI lifecycle in frontend/ipd.html --
everything the backend-only integration tests structurally cannot see, since the backend only
ever receives whatever the (possibly buggy) JS decided to send it. Uses the mocked
MediaRecorder infrastructure from tests/e2e/conftest.py (see tests/_voice_helpers.py's module
docstring for why the mock point is scribe.transcribe_audio, not the browser's recording
object -- the recorder mock only needs to produce SOME audio blob for the upload to carry).

Note on the toggle button's session model: with MediaRecorder, "populate the textarea" only
happens after an explicit Stop click uploads and transcribes the clip -- unlike the old
non-continuous SpeechRecognition, which fired onresult (and populated the textarea) as soon as
a fake result arrived, with no Stop click needed. Every test below that used to fire one mock
result now does an explicit Start-click / Stop-click pair per utterance.
"""
import json

import pytest

from tests.e2e.conftest import mint_tokens, queue_transcription_result, set_tokens_in_browser

pytestmark = pytest.mark.e2e


@pytest.fixture
def ipd_patient(make_user, db_session):
    from app.models import Patient, NurseAssignment

    head_nurse = make_user(email="head@e2e-mic.com", role="HeadNurse")
    nurse = make_user(email="nurse@e2e-mic.com", role="Nurse", organization_id=head_nurse.organization_id)
    patient = Patient(name="E2E Mic Patient", age=40, gender="F", ward="General",
                       organization_id=head_nurse.organization_id, created_by=head_nurse.id)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    db_session.add(NurseAssignment(patient_id=patient.id, nurse_id=nurse.id, assigned_by=head_nurse.id))
    db_session.commit()
    return nurse, patient


def _open_consult(js_page, live_server_url, user, patient):
    tokens = mint_tokens(user)
    set_tokens_in_browser(js_page, live_server_url, tokens["access_token"], tokens["refresh_token"])
    js_page.goto(f"{live_server_url}/ipd.html")
    js_page.wait_for_timeout(300)
    js_page.evaluate(f"openNursingConsult({patient.id})")
    js_page.wait_for_timeout(200)


def test_mic_button_toggles_listening_visual_state(js_page, live_server_url, ipd_patient, monkeypatch):
    # The .listening class drives a CSS `pulse` animation (continuously changing bounding box),
    # which fails Playwright's default click actionability "element is stable" check. force=True
    # bypasses that -- a real user's click isn't blocked by the button's own pulse animation.
    import app.main as app_main

    nurse, patient = ipd_patient
    queue_transcription_result(monkeypatch, app_main, "BP stable")
    _open_consult(js_page, live_server_url, nurse, patient)

    mic_btn = js_page.locator("#nursing-voice-btn")
    assert "listening" not in (mic_btn.get_attribute("class") or "")

    mic_btn.click(force=True)
    js_page.wait_for_timeout(100)
    assert "listening" in mic_btn.get_attribute("class")
    assert js_page.locator("#nursing-voice-status").inner_text() == "Recording..."

    mic_btn.click(force=True)  # clicking again while recording stops + uploads for transcription
    js_page.wait_for_timeout(150)
    assert "listening" not in (mic_btn.get_attribute("class") or "")
    assert js_page.js_errors == []


def test_single_recording_populates_textarea(js_page, live_server_url, ipd_patient, monkeypatch):
    import app.main as app_main

    nurse, patient = ipd_patient
    queue_transcription_result(monkeypatch, app_main, "BP 120 over 80, patient stable")
    _open_consult(js_page, live_server_url, nurse, patient)

    js_page.click("#nursing-voice-btn")
    js_page.wait_for_timeout(100)
    js_page.click("#nursing-voice-btn", force=True)  # stop -> upload -> transcribe
    js_page.wait_for_timeout(300)

    assert "BP 120 over 80, patient stable" in js_page.locator("#nursing-voice-text").input_value()
    assert js_page.js_errors == []


def test_multiple_recordings_accumulate_with_newlines(js_page, live_server_url, ipd_patient, monkeypatch):
    """A nurse who speaks, pauses (click stops+transcribes the first clip), and speaks again
    (click starts a fresh recording) should see both utterances preserved, not the second
    overwriting the first."""
    import app.main as app_main

    nurse, patient = ipd_patient
    queue_transcription_result(monkeypatch, app_main, "BP 120 over 80", "heart rate seventy two")
    _open_consult(js_page, live_server_url, nurse, patient)

    js_page.click("#nursing-voice-btn", force=True)  # start recording 1
    js_page.wait_for_timeout(100)
    js_page.click("#nursing-voice-btn", force=True)  # stop recording 1 -> transcribes to text 1
    js_page.wait_for_timeout(300)
    js_page.click("#nursing-voice-btn", force=True)  # start recording 2
    js_page.wait_for_timeout(100)
    js_page.click("#nursing-voice-btn", force=True)  # stop recording 2 -> transcribes to text 2
    js_page.wait_for_timeout(300)

    text = js_page.locator("#nursing-voice-text").input_value()
    assert "BP 120 over 80" in text
    assert "heart rate seventy two" in text
    assert js_page.js_errors == []


def test_transcription_failure_resets_ui_state(js_page, live_server_url, ipd_patient, monkeypatch):
    import app.main as app_main

    nurse, patient = ipd_patient

    def _raise(audio_bytes, content_type, filename):
        raise RuntimeError("upstream Groq error")

    monkeypatch.setattr(app_main.scribe, "transcribe_audio", _raise)
    _open_consult(js_page, live_server_url, nurse, patient)

    js_page.click("#nursing-voice-btn")
    js_page.wait_for_timeout(100)
    js_page.click("#nursing-voice-btn", force=True)
    js_page.wait_for_timeout(300)

    status = js_page.locator("#nursing-voice-status").inner_text()
    assert "failed" in status.lower()
    assert "listening" not in (js_page.locator("#nursing-voice-btn").get_attribute("class") or "")
    assert js_page.js_errors == []


def test_process_with_empty_textarea_shows_alert_and_makes_no_api_call(js_page, live_server_url, ipd_patient, monkeypatch):
    import app.main as app_main

    nurse, patient = ipd_patient
    call_count = {"n": 0}

    def _fake_call(prompt, system=None, temperature=0.3):
        call_count["n"] += 1
        return json.dumps({"vitals": [], "labs": [], "nursing_note": {}})

    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _fake_call)

    _open_consult(js_page, live_server_url, nurse, patient)
    js_page.fill("#nursing-voice-text", "")

    dialogs = []
    js_page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    js_page.click("#nursing-process-btn")
    js_page.wait_for_timeout(200)

    assert any("speak or type" in m.lower() for m in dialogs)
    assert call_count["n"] == 0, "Process must not call the extraction API with no input"
    assert js_page.js_errors == []


def test_process_then_edit_then_save_full_voice_round_trip(js_page, live_server_url, ipd_patient, monkeypatch):
    """The complete real nurse workflow: record -> Process (extract) -> review/edit the
    extracted vitals -> Save. Confirms the edited (not raw-extracted) values are what land in
    the database, exercising mapVitalsToStructured end-to-end via the real UI."""
    import app.main as app_main
    from app.models import Vital

    nurse, patient = ipd_patient

    def _fake_call(prompt, system=None, temperature=0.3):
        return json.dumps({
            "vitals": [{"parameter": "Heart Rate", "value": "70", "unit": "bpm"}],
            "labs": [], "nursing_note": {"subjective": "Feels okay", "objective": "", "assessment": "", "plan": ""},
        })

    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _fake_call)
    queue_transcription_result(monkeypatch, app_main, "heart rate seventy")

    _open_consult(js_page, live_server_url, nurse, patient)
    js_page.click("#nursing-voice-btn")
    js_page.wait_for_timeout(100)
    js_page.click("#nursing-voice-btn", force=True)
    js_page.wait_for_timeout(300)

    js_page.click("#nursing-process-btn")
    js_page.wait_for_timeout(400)

    # Nurse corrects the extracted value before saving (e.g. mis-heard by the LLM).
    js_page.fill(".vital-item input[placeholder='Value']", "74")

    js_page.on("dialog", lambda d: d.accept())
    js_page.click("#nursing-save-btn")
    js_page.wait_for_timeout(500)

    assert js_page.js_errors == []
    saved = (
        app_main.SessionLocal()
        .query(Vital)
        .filter(Vital.patient_id == patient.id)
        .order_by(Vital.recorded_at.desc())
        .first()
    )
    assert saved is not None
    assert saved.heart_rate == 74, "nurse's corrected value (74) should be saved, not the raw extraction (70)"


def test_reopening_modal_clears_previous_voice_session_state(js_page, live_server_url, ipd_patient, monkeypatch):
    import app.main as app_main

    nurse, patient = ipd_patient

    def _fake_call(prompt, system=None, temperature=0.3):
        return json.dumps({"vitals": [{"parameter": "HR", "value": "80", "unit": "bpm"}], "labs": [], "nursing_note": {}})

    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _fake_call)
    queue_transcription_result(monkeypatch, app_main, "heart rate eighty")

    _open_consult(js_page, live_server_url, nurse, patient)
    js_page.click("#nursing-voice-btn")
    js_page.wait_for_timeout(100)
    js_page.click("#nursing-voice-btn", force=True)
    js_page.wait_for_timeout(300)
    js_page.click("#nursing-process-btn")
    js_page.wait_for_timeout(400)
    assert js_page.locator("#nursing-voice-text").input_value() != ""

    js_page.click("#nursing-consult-modal .modal-close")
    js_page.wait_for_timeout(100)
    js_page.evaluate(f"openNursingConsult({patient.id})")
    js_page.wait_for_timeout(200)

    assert js_page.locator("#nursing-voice-text").input_value() == ""
    assert js_page.locator("#nursing-note-text").input_value() == ""
    assert js_page.js_errors == []


def test_nurse_role_sees_mic_button_nursing_station_does_not_reach_modal(js_page, live_server_url, make_user, ipd_patient, db_session):
    """NursingStation can still VIEW the read-only "Nursing Notes" tab (patient details are
    visible to that role), but must not see the action button that opens the voice-consult
    modal (📝 Nursing Notes, gated to Nurse/HeadNurse only in frontend/ipd.html) -- confirm the
    action button specifically is absent, distinct from the always-present tab of the same name."""
    nurse, patient = ipd_patient
    station = make_user(email="station@e2e-mic.com", role="NursingStation", organization_id=nurse.organization_id)
    tokens = mint_tokens(station)
    set_tokens_in_browser(js_page, live_server_url, tokens["access_token"], tokens["refresh_token"])
    js_page.goto(f"{live_server_url}/ipd.html")
    js_page.wait_for_timeout(300)
    js_page.evaluate(f"showPatientDetail({patient.id})")
    js_page.wait_for_timeout(300)

    action_btn = js_page.locator("button:has-text('📝 Nursing Notes')")
    assert action_btn.count() == 0
    read_only_tab = js_page.locator(".tab-btn:has-text('Nursing Notes')")
    assert read_only_tab.count() == 1, "NursingStation should still be able to view the read-only tab"

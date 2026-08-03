"""
Real-browser voice mic lifecycle specifically as HeadNurse -- parallel to
tests/e2e/test_ipd_voice_mic_lifecycle.py (which used a Nurse fixture), confirming the mic UI
and full voice workflow work identically for HeadNurse, including on a patient with no nurse
assignment at all (the one behavioral difference HeadNurse has from Nurse throughout this app).
"""
import json

import pytest

from tests.e2e.conftest import fire_speech_result, mint_tokens, set_tokens_in_browser

pytestmark = pytest.mark.e2e


@pytest.fixture
def unassigned_patient(make_user, db_session):
    from app.models import Patient

    head_nurse = make_user(email="head@e2e-hn-voice.com", role="HeadNurse")
    patient = Patient(name="E2E HN Voice Patient", age=48, gender="F", ward="General",
                       organization_id=head_nurse.organization_id, created_by=head_nurse.id)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    return head_nurse, patient


def _open_consult(js_page, live_server_url, user, patient):
    tokens = mint_tokens(user)
    set_tokens_in_browser(js_page, live_server_url, tokens["access_token"], tokens["refresh_token"])
    js_page.goto(f"{live_server_url}/headnurse.html")
    js_page.wait_for_timeout(300)
    js_page.evaluate(f"openNursingConsult({patient.id})")
    js_page.wait_for_timeout(200)


def test_headnurse_sees_nursing_notes_action_button(js_page, live_server_url, unassigned_patient):
    head_nurse, patient = unassigned_patient
    tokens = mint_tokens(head_nurse)
    set_tokens_in_browser(js_page, live_server_url, tokens["access_token"], tokens["refresh_token"])
    js_page.goto(f"{live_server_url}/headnurse.html")
    js_page.wait_for_timeout(300)
    js_page.evaluate(f"showPatientDetail({patient.id})")
    js_page.wait_for_timeout(300)
    assert js_page.locator("button:has-text('📝 Nursing Notes')").count() == 1


def test_headnurse_mic_button_works_on_unassigned_patient(js_page, live_server_url, unassigned_patient):
    """The core HeadNurse-vs-Nurse distinction: HeadNurse can voice-consult even on a patient
    nobody is assigned to yet."""
    head_nurse, patient = unassigned_patient
    _open_consult(js_page, live_server_url, head_nurse, patient)

    mic_btn = js_page.locator("#nursing-voice-btn")
    mic_btn.click(force=True)
    js_page.wait_for_timeout(100)
    assert "listening" in mic_btn.get_attribute("class")
    fire_speech_result(js_page, "patient stable, no complaints")
    js_page.wait_for_timeout(150)
    assert "patient stable, no complaints" in js_page.locator("#nursing-voice-text").input_value()
    assert js_page.js_errors == []


def test_headnurse_full_voice_round_trip_on_unassigned_patient(js_page, live_server_url, unassigned_patient, monkeypatch):
    import app.main as app_main
    from app.models import Vital, NursingNote

    head_nurse, patient = unassigned_patient

    def _fake_call(prompt, system=None, temperature=0.3):
        return json.dumps({
            "vitals": [{"parameter": "BP", "value": "118/76", "unit": "mmHg"}],
            "labs": [], "nursing_note": {"subjective": "Comfortable", "objective": "", "assessment": "", "plan": ""},
        })

    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _fake_call)

    _open_consult(js_page, live_server_url, head_nurse, patient)
    js_page.click("#nursing-voice-btn", force=True)
    js_page.wait_for_timeout(100)
    fire_speech_result(js_page, "BP 118 over 76, patient comfortable")
    js_page.wait_for_timeout(150)

    js_page.click("#nursing-process-btn")
    js_page.wait_for_timeout(400)

    js_page.on("dialog", lambda d: d.accept())
    js_page.click("#nursing-save-btn")
    js_page.wait_for_timeout(500)

    assert js_page.js_errors == []
    saved_vital = (
        app_main.SessionLocal().query(Vital).filter(Vital.patient_id == patient.id)
        .order_by(Vital.recorded_at.desc()).first()
    )
    assert saved_vital is not None
    assert saved_vital.bp_systolic == 118
    assert saved_vital.bp_diastolic == 76
    saved_note = (
        app_main.SessionLocal().query(NursingNote).filter(NursingNote.patient_id == patient.id)
        .order_by(NursingNote.created_at.desc()).first()
    )
    assert saved_note is not None
    assert "Comfortable" in saved_note.notes


def test_headnurse_process_empty_textarea_shows_alert_no_api_call(js_page, live_server_url, unassigned_patient, monkeypatch):
    import app.main as app_main

    head_nurse, patient = unassigned_patient
    call_count = {"n": 0}

    def _fake_call(prompt, system=None, temperature=0.3):
        call_count["n"] += 1
        return json.dumps({"vitals": [], "labs": [], "nursing_note": {}})

    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _fake_call)
    _open_consult(js_page, live_server_url, head_nurse, patient)
    js_page.fill("#nursing-voice-text", "")

    dialogs = []
    js_page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    js_page.click("#nursing-process-btn")
    js_page.wait_for_timeout(200)

    assert any("speak or type" in m.lower() for m in dialogs)
    assert call_count["n"] == 0


def test_headnurse_can_type_instead_of_speaking(js_page, live_server_url, unassigned_patient, monkeypatch):
    """Voice is optional -- HeadNurse can type the narrative directly into the textarea."""
    import app.main as app_main

    head_nurse, patient = unassigned_patient

    def _fake_call(prompt, system=None, temperature=0.3):
        return json.dumps({"vitals": [], "labs": [], "nursing_note": {"subjective": "Typed note", "objective": "", "assessment": "", "plan": ""}})

    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _fake_call)
    _open_consult(js_page, live_server_url, head_nurse, patient)
    js_page.fill("#nursing-voice-text", "Patient reports feeling much better today")
    js_page.click("#nursing-process-btn")
    js_page.wait_for_timeout(400)
    assert "Typed note" in js_page.locator("#nursing-note-text").input_value()
    assert js_page.js_errors == []


def test_headnurse_reopening_modal_across_different_patients_resets_state(js_page, live_server_url, unassigned_patient, make_user, db_session):
    from app.models import Patient

    head_nurse, patient1 = unassigned_patient
    patient2 = Patient(name="Second HN Voice Patient", ward="General", bed="V2",
                        organization_id=head_nurse.organization_id, created_by=head_nurse.id)
    db_session.add(patient2)
    db_session.commit()
    db_session.refresh(patient2)

    _open_consult(js_page, live_server_url, head_nurse, patient1)
    js_page.fill("#nursing-voice-text", "Notes about patient 1")
    js_page.click("#nursing-consult-modal .modal-close")
    js_page.wait_for_timeout(100)

    js_page.evaluate(f"openNursingConsult({patient2.id})")
    js_page.wait_for_timeout(200)
    assert js_page.locator("#nursing-voice-text").input_value() == ""
    assert js_page.js_errors == []


def test_headnurse_voice_error_event_handled_gracefully(js_page, live_server_url, unassigned_patient):
    head_nurse, patient = unassigned_patient
    _open_consult(js_page, live_server_url, head_nurse, patient)
    js_page.click("#nursing-voice-btn", force=True)
    js_page.wait_for_timeout(100)
    js_page.evaluate(
        """() => {
            const rec = window.__mockInstances[window.__mockInstances.length - 1];
            rec.onerror({ error: 'audio-capture' });
        }"""
    )
    js_page.wait_for_timeout(100)
    assert "audio-capture" in js_page.locator("#nursing-voice-status").inner_text()
    assert js_page.js_errors == []

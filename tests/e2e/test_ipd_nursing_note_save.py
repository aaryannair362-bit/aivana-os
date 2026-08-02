"""
Real-browser regression test for the IPD nursing-consult voice flow (frontend/ipd.html):
mic -> "Process" (LLM extracts vitals/labs/note for review) -> nurse edits the note -> "Save".

Manual investigation of the "data not getting filled" bug report found that Save always
resent the raw voice_text alongside the reviewed note. backend/app/main.py's
create_nursing_note re-runs its own LLM extraction whenever voice_text is present, silently
discarding whatever the nurse had just reviewed and edited and persisting a second,
independently-generated (and here, deliberately different) note instead -- while the UI still
said "saved successfully". Fixed by no longer sending voice_text at save time and by properly
splitting the reviewed SOAP-formatted textarea back into its four fields.
"""
import pytest

from tests.e2e.conftest import fire_speech_result, mint_tokens, set_tokens_in_browser

pytestmark = pytest.mark.e2e


@pytest.fixture
def ipd_patient(make_user, db_session):
    from app.models import Patient

    head_nurse = make_user(email="head@e2e-ipd.com", role="HeadNurse")
    patient = Patient(name="E2E IPD Patient", age=45, gender="F", ward="General",
                       organization_id=head_nurse.organization_id, created_by=head_nurse.id)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    return head_nurse, patient


def test_save_persists_nurses_edited_note_not_a_fresh_llm_rederivation(
    js_page, live_server_url, ipd_patient, monkeypatch
):
    import app.main as app_main
    from app.models import NursingNote

    head_nurse, patient = ipd_patient
    call_count = {"n": 0}
    process_result = {
        "vitals": [], "labs": [],
        "nursing_note": {"subjective": "Initial extraction", "objective": "", "assessment": "", "plan": ""},
    }

    def _fake_call(prompt, system=None, temperature=0.3):
        call_count["n"] += 1
        # If Save wrongly resent voice_text, this would be called a second time and the
        # nurse's edits would be overwritten with this obviously-wrong marker text.
        import json
        return json.dumps(process_result if call_count["n"] == 1 else
                           {"subjective": "SHOULD NEVER BE SAVED", "objective": "", "assessment": "", "plan": ""})

    monkeypatch.setattr(app_main.scribe, "_call_groq_api", _fake_call)

    tokens = mint_tokens(head_nurse)
    set_tokens_in_browser(js_page, live_server_url, tokens["access_token"], tokens["refresh_token"])

    js_page.goto(f"{live_server_url}/ipd.html")
    js_page.wait_for_timeout(400)
    js_page.evaluate(f"openNursingConsult({patient.id})")
    js_page.wait_for_timeout(200)

    js_page.click("#nursing-voice-btn")
    js_page.wait_for_timeout(100)
    fire_speech_result(js_page, "patient reports mild headache")
    js_page.wait_for_timeout(150)

    js_page.click("#nursing-process-btn")
    js_page.wait_for_timeout(400)

    edited_note = (
        "Subjective: Patient reports headache, denies nausea.\n"
        "Objective: BP 118/76.\n"
        "Assessment: Stable, tension headache likely.\n"
        "Plan: Paracetamol PRN, reassess in 2h."
    )
    js_page.fill("#nursing-note-text", edited_note)

    def _accept_dialog(dialog):
        dialog.accept()
    js_page.on("dialog", _accept_dialog)

    js_page.click("#nursing-save-btn")
    js_page.wait_for_timeout(600)

    assert js_page.js_errors == [], f"unexpected JS errors: {js_page.js_errors}"
    assert call_count["n"] == 1, (
        f"expected exactly 1 LLM call (Process only), got {call_count['n']} -- "
        "Save is re-deriving the note instead of persisting the nurse's edits"
    )

    saved = (
        app_main.SessionLocal()
        .query(NursingNote)
        .filter(NursingNote.patient_id == patient.id)
        .order_by(NursingNote.created_at.desc())
        .first()
    )
    assert saved is not None, "no NursingNote row was persisted"
    assert "Patient reports headache, denies nausea" in saved.notes
    assert "tension headache likely" in saved.notes
    assert "SHOULD NEVER BE SAVED" not in saved.notes

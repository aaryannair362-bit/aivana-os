"""
Real-browser end-to-end coverage of the HeadNurse role on its own dedicated page,
frontend/headnurse.html. Specifically regression-tests two UI-only bugs found by auditing every
role-gated element against the backend's actual permission rules (a backend-only test suite
structurally cannot see these -- the backend always allowed both actions, but the button that
triggers them was hidden):

1. The "Admit Patient" button was only ever shown for NursingStation, even though
   POST /api/ipd/patients has always allowed HeadNurse too -- a head nurse had no UI path to
   admit a patient at all.
2. The "Mark Complete" task button was only ever shown for the assigned Nurse, even though
   PATCH /api/ipd/tasks/{id} has always allowed HeadNurse to update ANY task -- a head nurse
   who created a task had no UI path to complete it themselves.

Also covers HeadNurse's own dashboard (real KPI tiles from GET /api/ipd/dashboard-summary,
replacing frontend/ipd.html's old ward-summary stat bar now that HeadNurse has moved off that
page), nurse-workload visibility in the assign dropdown, and the unassign action.
"""
import pytest

from tests.e2e.conftest import mint_tokens, set_tokens_in_browser

pytestmark = pytest.mark.e2e


@pytest.fixture
def ward_setup(make_user, db_session):
    from app.models import Patient, NurseAssignment, Task

    head_nurse = make_user(email="head@e2e-hn.com", role="HeadNurse")
    nurse = make_user(email="nurse@e2e-hn.com", role="Nurse", organization_id=head_nurse.organization_id)
    patient = Patient(name="E2E HeadNurse Patient", age=55, gender="M", ward="General", bed="H1",
                       organization_id=head_nurse.organization_id, created_by=head_nurse.id)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    db_session.add(NurseAssignment(patient_id=patient.id, nurse_id=nurse.id, assigned_by=head_nurse.id))
    task = Task(patient_id=patient.id, nurse_id=nurse.id, assigned_by=head_nurse.id,
                description="E2E task for mark-complete regression test", status="Pending")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return head_nurse, nurse, patient, task


def _login(js_page, live_server_url, user):
    tokens = mint_tokens(user)
    set_tokens_in_browser(js_page, live_server_url, tokens["access_token"], tokens["refresh_token"])
    js_page.goto(f"{live_server_url}/headnurse.html")
    js_page.wait_for_timeout(300)


def test_headnurse_sees_admit_patient_button(js_page, live_server_url, ward_setup):
    """Regression test for the admit-button visibility bug (fixed in an earlier pass)."""
    head_nurse, nurse, patient, task = ward_setup
    _login(js_page, live_server_url, head_nurse)
    js_page.click("button[data-view='patients']")
    js_page.wait_for_timeout(200)
    admit_btn = js_page.locator("#show-admit-btn")
    assert admit_btn.is_visible(), "HeadNurse must see the Admit Patient button (backend always allowed this)"
    assert js_page.js_errors == []


def test_headnurse_can_admit_a_patient_through_the_ui(js_page, live_server_url, ward_setup):
    head_nurse, nurse, patient, task = ward_setup
    _login(js_page, live_server_url, head_nurse)
    js_page.click("button[data-view='patients']")
    js_page.wait_for_timeout(200)
    js_page.click("#show-admit-btn")
    js_page.wait_for_timeout(150)
    js_page.fill("#admit-name", "UI Admitted Patient")
    js_page.fill("#admit-ward", "ICU")
    js_page.fill("#admit-bed", "9")

    js_page.on("dialog", lambda d: d.accept())
    js_page.click("#admit-submit")
    js_page.wait_for_timeout(400)

    assert js_page.js_errors == []
    assert "UI Admitted Patient" in js_page.locator("#patient-list").inner_text()


def test_headnurse_sees_mark_complete_on_any_nurses_task_in_patient_detail(js_page, live_server_url, ward_setup):
    """Regression test for the Mark Complete visibility bug (fixed in an earlier pass) -- in the
    patient-detail Tasks tab."""
    head_nurse, nurse, patient, task = ward_setup
    _login(js_page, live_server_url, head_nurse)
    js_page.evaluate(f"showPatientDetail({patient.id})")
    js_page.wait_for_timeout(300)
    js_page.click(".tab-btn[data-tab='tasks-tab']")
    js_page.wait_for_timeout(150)

    mark_complete_btn = js_page.locator("#tasks-tab button:has-text('Mark Complete')")
    assert mark_complete_btn.count() == 1, "HeadNurse must see Mark Complete on nurse_a's task (backend always allowed this)"
    assert js_page.js_errors == []


def test_headnurse_can_mark_a_nurses_task_complete_through_the_ui(js_page, live_server_url, ward_setup):
    head_nurse, nurse, patient, task = ward_setup
    _login(js_page, live_server_url, head_nurse)
    js_page.evaluate(f"showPatientDetail({patient.id})")
    js_page.wait_for_timeout(300)
    js_page.click(".tab-btn[data-tab='tasks-tab']")
    js_page.wait_for_timeout(150)

    js_page.on("dialog", lambda d: d.accept())
    js_page.click("#tasks-tab button:has-text('Mark Complete')", force=True)
    js_page.wait_for_timeout(400)

    assert js_page.js_errors == []
    import app.main as app_main
    from app.models import Task
    refreshed = app_main.SessionLocal().query(Task).filter(Task.id == task.id).first()
    assert refreshed.status == "Completed"


def test_headnurse_sees_mark_complete_in_global_tasks_view(js_page, live_server_url, ward_setup):
    head_nurse, nurse, patient, task = ward_setup
    _login(js_page, live_server_url, head_nurse)
    js_page.click("button[data-view='tasks']")
    js_page.wait_for_timeout(400)
    mark_complete_btn = js_page.locator("#task-list button:has-text('Mark Complete')")
    assert mark_complete_btn.count() == 1
    assert js_page.js_errors == []


def test_headnurse_dashboard_kpi_tiles_reflect_real_counts(js_page, live_server_url, ward_setup):
    """The dashboard KPI tiles (from GET /api/ipd/dashboard-summary) replace frontend/ipd.html's
    old ward-summary stat bar now that HeadNurse has its own page -- confirms they're wired to
    real numbers, not the reference mockup's hardcoded-and-disconnected values."""
    head_nurse, nurse, patient, task = ward_setup
    _login(js_page, live_server_url, head_nurse)
    assert js_page.locator("#kpi-total-patients").inner_text() == "1"
    assert js_page.locator("#kpi-assigned-patients").inner_text() == "1"
    assert js_page.locator("#kpi-pending-tasks").inner_text() == "1"
    assert js_page.locator("#kpi-completed-tasks").inner_text() == "0"
    assert js_page.js_errors == []


def test_dashboard_kpis_update_after_admitting_an_unassigned_patient(js_page, live_server_url, ward_setup):
    head_nurse, nurse, patient, task = ward_setup
    _login(js_page, live_server_url, head_nurse)
    js_page.click("button[data-view='patients']")
    js_page.wait_for_timeout(150)
    js_page.click("#show-admit-btn")
    js_page.fill("#admit-name", "Unassigned Summary Patient")
    js_page.fill("#admit-ward", "General")
    js_page.on("dialog", lambda d: d.accept())
    js_page.click("#admit-submit")
    js_page.wait_for_timeout(300)
    js_page.click("button[data-view='dashboard']")
    js_page.wait_for_timeout(300)
    # Total patients grows to 2 (the fixture's assigned patient + the newly admitted unassigned
    # one); assigned_patients stays at 1 since the new patient has no nurse.
    assert js_page.locator("#kpi-total-patients").inner_text() == "2"
    assert js_page.locator("#kpi-assigned-patients").inner_text() == "1"


def test_headnurse_sees_nurse_workload_in_assign_dropdown(js_page, live_server_url, ward_setup):
    head_nurse, nurse, patient, task = ward_setup
    _login(js_page, live_server_url, head_nurse)
    js_page.click("button[data-view='assign']")
    js_page.wait_for_timeout(300)
    options_text = js_page.locator("#assign-nurse").inner_text()
    assert "1 patient" in options_text or "patients)" in options_text
    assert js_page.js_errors == []


def test_headnurse_sees_currently_assigned_nurse_in_patient_dropdown(js_page, live_server_url, ward_setup):
    head_nurse, nurse, patient, task = ward_setup
    _login(js_page, live_server_url, head_nurse)
    js_page.click("button[data-view='assign']")
    js_page.wait_for_timeout(300)
    options_text = js_page.locator("#assign-patient").inner_text()
    assert nurse.email in options_text


def test_headnurse_unassign_button_visible_and_works(js_page, live_server_url, ward_setup):
    head_nurse, nurse, patient, task = ward_setup
    _login(js_page, live_server_url, head_nurse)
    js_page.evaluate(f"showPatientDetail({patient.id})")
    js_page.wait_for_timeout(300)

    unassign_btn = js_page.locator("button:has-text('Unassign Nurse')")
    assert unassign_btn.count() == 1

    js_page.on("dialog", lambda d: d.accept())
    unassign_btn.click()
    js_page.wait_for_timeout(400)

    assert js_page.js_errors == []
    import app.main as app_main
    from app.models import NurseAssignment
    active = (
        app_main.SessionLocal()
        .query(NurseAssignment)
        .filter(NurseAssignment.patient_id == patient.id, NurseAssignment.status == "Active")
        .count()
    )
    assert active == 0


def test_unassign_button_not_shown_when_no_nurse_assigned(js_page, live_server_url, make_user, db_session):
    from app.models import Patient
    head_nurse = make_user(email="head2@e2e-hn.com", role="HeadNurse")
    patient = Patient(name="Never Assigned E2E", ward="General", bed="Z1",
                       organization_id=head_nurse.organization_id, created_by=head_nurse.id)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)

    _login(js_page, live_server_url, head_nurse)
    js_page.evaluate(f"showPatientDetail({patient.id})")
    js_page.wait_for_timeout(300)
    assert js_page.locator("button:has-text('Unassign Nurse')").count() == 0


def test_headnurse_discharge_still_works_alongside_new_features(js_page, live_server_url, ward_setup):
    """Regression check that the discharge action (added in an earlier pass) still coexists
    correctly with the Unassign button in the same action row."""
    head_nurse, nurse, patient, task = ward_setup
    _login(js_page, live_server_url, head_nurse)
    js_page.evaluate(f"showPatientDetail({patient.id})")
    js_page.wait_for_timeout(300)
    assert js_page.locator("button:has-text('🚪 Discharge')").count() == 1
    assert js_page.locator("button:has-text('Unassign Nurse')").count() == 1
    assert js_page.js_errors == []


def test_full_headnurse_ui_session_no_console_errors(js_page, live_server_url, ward_setup):
    """Broad smoke pass: click through every HeadNurse sidebar view (Dashboard/Patients/Assign/
    Tasks/Calendar/Reports) and every patient-drawer tab in one session, confirm zero uncaught
    JS errors anywhere -- the class of bug a backend-only suite can't see."""
    head_nurse, nurse, patient, task = ward_setup
    _login(js_page, live_server_url, head_nurse)
    for view in ["dashboard", "patients", "assign", "tasks", "calendar", "reports"]:
        js_page.click(f"button[data-view='{view}']")
        js_page.wait_for_timeout(250)
    js_page.evaluate(f"showPatientDetail({patient.id})")
    js_page.wait_for_timeout(300)
    for tab in ["overview-tab", "vitals-tab", "medication-tab", "tasks-tab", "nursing-tab", "discharge-summary-tab"]:
        js_page.click(f".tab-btn[data-tab='{tab}']")
        js_page.wait_for_timeout(150)
    assert js_page.js_errors == []

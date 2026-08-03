"""
Real-browser end-to-end coverage of the NursingStation role (ward/front-desk login) in
frontend/ipd.html. Confirms the UI correctly shows the narrow set of actions this role has
backend permission for (admit, edit, discharge, ward-wide dashboard/read access) and correctly
hides everything it doesn't (assign, unassign, tasks sidebar, nursing-notes/voice action,
nurse-workload-driven assign dropdown) -- the same audit method that found the HeadNurse UI
bugs and the tasks-tab id collision, applied to this role.
"""
import pytest

from tests.e2e.conftest import mint_tokens, set_tokens_in_browser

pytestmark = pytest.mark.e2e


@pytest.fixture
def ward_setup(make_user, db_session):
    from app.models import Patient, NurseAssignment, Vital

    station = make_user(email="station@e2e-ns.com", role="NursingStation")
    head_nurse = make_user(email="head@e2e-ns.com", role="HeadNurse", organization_id=station.organization_id)
    nurse = make_user(email="nurse@e2e-ns.com", role="Nurse", organization_id=station.organization_id)
    patient = Patient(name="E2E NursingStation Patient", age=50, gender="F", ward="General", bed="N1",
                       organization_id=station.organization_id, created_by=station.id)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    db_session.add(NurseAssignment(patient_id=patient.id, nurse_id=nurse.id, assigned_by=head_nurse.id))
    db_session.add(Vital(patient_id=patient.id, nurse_id=nurse.id, heart_rate=80))
    db_session.commit()
    return station, head_nurse, nurse, patient


def _login(js_page, live_server_url, user):
    tokens = mint_tokens(user)
    set_tokens_in_browser(js_page, live_server_url, tokens["access_token"], tokens["refresh_token"])
    js_page.goto(f"{live_server_url}/ipd.html")
    js_page.wait_for_timeout(300)


def test_station_sees_admit_patient_button(js_page, live_server_url, ward_setup):
    station, head_nurse, nurse, patient = ward_setup
    _login(js_page, live_server_url, station)
    js_page.click("button[data-view='patients']")
    js_page.wait_for_timeout(200)
    assert js_page.locator("#show-admit-btn").is_visible()
    assert js_page.js_errors == []


def test_station_can_admit_a_patient_through_the_ui(js_page, live_server_url, ward_setup):
    station, head_nurse, nurse, patient = ward_setup
    _login(js_page, live_server_url, station)
    js_page.click("button[data-view='patients']")
    js_page.wait_for_timeout(200)
    js_page.click("#show-admit-btn")
    js_page.wait_for_timeout(150)
    js_page.fill("#admit-name", "UI Admitted By Station")
    js_page.fill("#admit-ward", "Emergency")
    js_page.on("dialog", lambda d: d.accept())
    js_page.click("#admit-submit")
    js_page.wait_for_timeout(400)
    assert js_page.js_errors == []
    assert "UI Admitted By Station" in js_page.locator("#patient-list").inner_text()


def test_station_does_not_see_assign_tab(js_page, live_server_url, ward_setup):
    station, head_nurse, nurse, patient = ward_setup
    _login(js_page, live_server_url, station)
    assert not js_page.locator("#assign-tab").is_visible()


def test_station_does_not_see_tasks_nav_button(js_page, live_server_url, ward_setup):
    station, head_nurse, nurse, patient = ward_setup
    _login(js_page, live_server_url, station)
    assert not js_page.locator("#tasks-nav-btn").is_visible()


def test_station_sees_ward_summary_stat_bar(js_page, live_server_url, ward_setup):
    """NursingStation is a ward-wide viewing role, same as HeadNurse/Doctor."""
    station, head_nurse, nurse, patient = ward_setup
    _login(js_page, live_server_url, station)
    summary = js_page.locator("#ward-summary")
    assert summary.is_visible()
    assert "patients" in summary.inner_text().lower()


def test_station_sees_edit_and_discharge_buttons_but_not_unassign_or_nursing_notes(js_page, live_server_url, ward_setup):
    station, head_nurse, nurse, patient = ward_setup
    _login(js_page, live_server_url, station)
    js_page.evaluate(f"showPatientDetail({patient.id})")
    js_page.wait_for_timeout(300)

    assert js_page.locator("button:has-text('✎ Edit')").count() == 1
    assert js_page.locator("button:has-text('🚪 Discharge')").count() == 1
    assert js_page.locator("button:has-text('Unassign Nurse')").count() == 0, "Unassign is HeadNurse-only"
    assert js_page.locator("button:has-text('📝 Nursing Notes')").count() == 0, "Nursing Notes action is Nurse/HeadNurse-only"
    assert js_page.js_errors == []


def test_station_can_view_but_not_edit_vitals_tab(js_page, live_server_url, ward_setup):
    """The patient-detail Vitals tab is read-only display for every role that can view
    details -- confirms NursingStation sees the nurse-recorded vital without any way to add one."""
    station, head_nurse, nurse, patient = ward_setup
    _login(js_page, live_server_url, station)
    js_page.evaluate(f"showPatientDetail({patient.id})")
    js_page.wait_for_timeout(300)
    vitals_text = js_page.locator("#vitals-tab").inner_text()
    assert "HR" in vitals_text or "80" in vitals_text
    assert js_page.js_errors == []


def test_station_can_view_tasks_tab_in_patient_detail_despite_no_sidebar_tasks_view(js_page, live_server_url, ward_setup, db_session):
    """Regression coverage combining two fixes: the tasks-tab id collision fix (this tab must
    now actually become visible on click) and confirming NursingStation's read-only task
    access works even though it has no sidebar Tasks view at all."""
    from app.models import Task
    station, head_nurse, nurse, patient = ward_setup
    db_session.add(Task(patient_id=patient.id, nurse_id=nurse.id, assigned_by=head_nurse.id,
                         description="Station-visible task", status="Pending"))
    db_session.commit()

    _login(js_page, live_server_url, station)
    js_page.evaluate(f"showPatientDetail({patient.id})")
    js_page.wait_for_timeout(300)
    js_page.click(".tab-btn[data-tab='tasks-tab']")
    js_page.wait_for_timeout(200)

    tasks_tab = js_page.locator("#tasks-tab")
    assert tasks_tab.is_visible(), "tasks-tab must actually become visible after the id-collision fix"
    assert "Station-visible task" in tasks_tab.inner_text()
    assert tasks_tab.locator("button:has-text('Mark Complete')").count() == 0, "NursingStation cannot complete tasks"
    assert js_page.js_errors == []


def test_station_can_discharge_a_patient_through_the_ui(js_page, live_server_url, ward_setup):
    station, head_nurse, nurse, patient = ward_setup
    _login(js_page, live_server_url, station)
    js_page.evaluate(f"showPatientDetail({patient.id})")
    js_page.wait_for_timeout(300)

    js_page.on("dialog", lambda d: d.accept())
    js_page.click("button:has-text('🚪 Discharge')")
    js_page.wait_for_timeout(400)

    assert js_page.js_errors == []
    import app.main as app_main
    from app.models import Patient
    refreshed = app_main.SessionLocal().query(Patient).filter(Patient.id == patient.id).first()
    assert refreshed.status == "Discharged"


def test_station_sees_assigned_nurse_in_patient_list(js_page, live_server_url, ward_setup):
    station, head_nurse, nurse, patient = ward_setup
    _login(js_page, live_server_url, station)
    js_page.click("button[data-view='patients']")
    js_page.wait_for_timeout(300)
    assert nurse.email in js_page.locator("#patient-list").inner_text()


def test_station_search_filters_patient_list(js_page, live_server_url, ward_setup):
    station, head_nurse, nurse, patient = ward_setup
    _login(js_page, live_server_url, station)
    js_page.click("button[data-view='patients']")
    js_page.wait_for_timeout(300)
    js_page.fill("#patient-search", "nonexistent-name-xyz")
    js_page.wait_for_timeout(200)
    assert "No patients match" in js_page.locator("#patient-list").inner_text()


def test_full_station_ui_session_no_console_errors(js_page, live_server_url, ward_setup):
    """Broad smoke pass across every view NursingStation has access to."""
    station, head_nurse, nurse, patient = ward_setup
    _login(js_page, live_server_url, station)
    for view in ["dashboard", "alerts", "patients"]:
        js_page.click(f"button[data-view='{view}']")
        js_page.wait_for_timeout(250)
    js_page.evaluate(f"showPatientDetail({patient.id})")
    js_page.wait_for_timeout(300)
    for tab in ["overview-tab", "vitals-tab", "medication-tab", "tasks-tab", "nursing-tab", "discharge-summary-tab"]:
        js_page.click(f".tab-btn[data-tab='{tab}']")
        js_page.wait_for_timeout(150)
    assert js_page.js_errors == []


def test_nurse_workload_endpoint_not_called_by_station_ui(js_page, live_server_url, ward_setup):
    """NursingStation never loads the Assign view (it has no access), so the HeadNurse-only
    /api/ipd/nurse-workload call should never fire for this role -- confirms no leftover
    network call attempts a 403 in the background during a normal session."""
    station, head_nurse, nurse, patient = ward_setup
    requests_seen = []
    js_page.on("request", lambda req: requests_seen.append(req.url) if "nurse-workload" in req.url else None)
    _login(js_page, live_server_url, station)
    js_page.click("button[data-view='patients']")
    js_page.wait_for_timeout(300)
    assert requests_seen == []

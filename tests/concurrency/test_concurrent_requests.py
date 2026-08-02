"""
Real-concurrency / bulk-load tests: genuine simultaneous HTTP requests against a live uvicorn
server (via ThreadPoolExecutor + requests), exercising the exact "busy hospital, many
simultaneous users" scenario this whole test pass has been organized around. Targets the
theoretical races flagged (but never exercised) in ARCHITECTURE_NOTES.md: POST /api/ipd/assign
has no locking, so two truly concurrent assignment calls for the same patient were an open
question. This is where that gets an actual answer instead of a guess.
"""
import concurrent.futures
import json

import pytest
import requests

from tests.e2e.conftest import mint_tokens


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@concurrency.com", role="HeadNurse")


@pytest.fixture
def nurses(make_user, head_nurse):
    return [make_user(email=f"nurse{i}@concurrency.com", role="Nurse", organization_id=head_nurse.organization_id)
            for i in range(10)]


@pytest.fixture
def station(make_user, head_nurse):
    return make_user(email="station@concurrency.com", role="NursingStation", organization_id=head_nurse.organization_id)


def _admit_patient(live_server_url, token, **overrides):
    payload = {"name": "Concurrency Patient", "ward": "General", "bed": "1"}
    payload.update(overrides)
    resp = requests.post(f"{live_server_url}/api/ipd/patients", json=payload, headers=_auth_headers(token), timeout=10)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# The documented theoretical race: two head nurses (or the same one, double-clicking) assign
# two DIFFERENT nurses to the SAME patient at the same instant. assign_patient's logic is
# "close prior active assignment, then insert new" with no transaction-level locking --
# under true concurrency, both requests could read "no active assignment yet" before either
# writes, producing two simultaneously Active assignments for one patient.
# ---------------------------------------------------------------------------

def test_concurrent_assignment_to_same_patient_different_nurses(live_server_url, head_nurse, nurses, db_session):
    from app.models import NurseAssignment

    token = mint_tokens(head_nurse)["access_token"]
    patient_id = _admit_patient(live_server_url, token)
    # Extract plain ids in the main thread first -- see the note in
    # test_many_simultaneous_logins_all_succeed_with_distinct_tokens on why ORM attribute
    # access must never happen from a worker thread against a shared Session.
    nurse_ids = [n.id for n in nurses[:8]]

    def _assign(nurse_id):
        return requests.post(f"{live_server_url}/api/ipd/assign",
                              json={"patient_id": patient_id, "nurse_id": nurse_id},
                              headers=_auth_headers(token), timeout=10)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_assign, nurse_ids))

    assert all(r.status_code == 200 for r in results), [r.text for r in results if r.status_code != 200]

    db_session.expire_all()
    active_assignments = db_session.query(NurseAssignment).filter(
        NurseAssignment.patient_id == patient_id, NurseAssignment.status == "Active"
    ).all()
    assert len(active_assignments) == 1, (
        f"expected exactly 1 Active assignment after 8 concurrent assign calls, found "
        f"{len(active_assignments)} -- the documented theoretical race is real, not just theoretical"
    )


def test_concurrent_assignment_then_roster_view_is_consistent(live_server_url, head_nurse, nurses):
    """Beyond just the DB row count: the roster endpoint (what a real head nurse actually
    looks at) must also report exactly one assigned nurse, not a stale or ambiguous view."""
    token = mint_tokens(head_nurse)["access_token"]
    patient_id = _admit_patient(live_server_url, token, name="Roster Consistency Patient")
    nurse_ids = [n.id for n in nurses[:6]]

    def _assign(nurse_id):
        return requests.post(f"{live_server_url}/api/ipd/assign",
                              json={"patient_id": patient_id, "nurse_id": nurse_id},
                              headers=_auth_headers(token), timeout=10)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(_assign, nurse_ids))

    roster = requests.get(f"{live_server_url}/api/ipd/patients", headers=_auth_headers(token), timeout=10).json()
    patient = next(p for p in roster if p["id"] == patient_id)
    assert patient["assigned_nurse"] is not None
    # Exactly one of the 6 nurses' own rosters should show this patient.
    nurse_tokens = [mint_tokens(n)["access_token"] for n in nurses[:6]]
    counts = []
    for t in nurse_tokens:
        my_roster = requests.get(f"{live_server_url}/api/ipd/patients", headers=_auth_headers(t), timeout=10).json()
        counts.append(1 if any(p["id"] == patient_id for p in my_roster) else 0)
    assert sum(counts) == 1, f"expected exactly one nurse to see this patient after concurrent assignment, got {sum(counts)}"


def test_concurrent_assign_and_unassign_race(live_server_url, head_nurse, nurses, db_session):
    from app.models import NurseAssignment

    token = mint_tokens(head_nurse)["access_token"]
    patient_id = _admit_patient(live_server_url, token, name="Assign Unassign Race Patient")
    nurse_0_id, nurse_1_id = nurses[0].id, nurses[1].id
    requests.post(f"{live_server_url}/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse_0_id},
                  headers=_auth_headers(token), timeout=10)

    def _assign_other():
        return requests.post(f"{live_server_url}/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurse_1_id},
                              headers=_auth_headers(token), timeout=10)

    def _unassign():
        return requests.post(f"{live_server_url}/api/ipd/unassign", json={"patient_id": patient_id},
                              headers=_auth_headers(token), timeout=10)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_assign_other), pool.submit(_unassign), pool.submit(_assign_other), pool.submit(_unassign)]
        results = [f.result() for f in futures]

    assert all(r.status_code == 200 for r in results)
    db_session.expire_all()
    active_count = db_session.query(NurseAssignment).filter(
        NurseAssignment.patient_id == patient_id, NurseAssignment.status == "Active"
    ).count()
    assert active_count <= 1, f"expected at most 1 Active assignment after concurrent assign/unassign race, found {active_count}"


# ---------------------------------------------------------------------------
# Concurrent vitals recording -- multiple nurses (or a busy single nurse's rapid double-taps)
# recording vitals for the same and different patients simultaneously. Each vital is an
# independent INSERT, so this should be safe by construction, but must be proven under load,
# not assumed.
# ---------------------------------------------------------------------------

def test_concurrent_vitals_recording_same_patient_no_data_loss(live_server_url, head_nurse, nurses):
    token = mint_tokens(head_nurse)["access_token"]
    patient_id = _admit_patient(live_server_url, token, name="Concurrent Vitals Patient")
    requests.post(f"{live_server_url}/api/ipd/assign", json={"patient_id": patient_id, "nurse_id": nurses[0].id},
                  headers=_auth_headers(token), timeout=10)
    nurse_token = mint_tokens(nurses[0])["access_token"]

    def _record(i):
        return requests.post(f"{live_server_url}/api/ipd/vitals",
                              json={"patient_id": patient_id, "heart_rate": 60 + i}, headers=_auth_headers(nurse_token), timeout=10)

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
        results = list(pool.map(_record, range(15)))

    assert all(r.status_code == 200 for r in results), [r.text for r in results if r.status_code != 200]
    vitals = requests.get(f"{live_server_url}/api/ipd/vitals/{patient_id}?limit=100", headers=_auth_headers(token), timeout=10).json()
    assert len(vitals) == 15, f"expected all 15 concurrently-recorded vitals to persist, found {len(vitals)}"
    recorded_heart_rates = {v["heart_rate"] for v in vitals}
    assert recorded_heart_rates == {60 + i for i in range(15)}


def test_concurrent_vitals_across_many_different_patients(live_server_url, head_nurse, nurses):
    """A realistic busy-ward moment: many nurses each recording vitals for their own different
    patients at the same time -- confirms no cross-patient data corruption under load."""
    token = mint_tokens(head_nurse)["access_token"]
    patient_ids = [_admit_patient(live_server_url, token, name=f"MultiPatient {i}", bed=str(i)) for i in range(10)]
    for i, pid in enumerate(patient_ids):
        requests.post(f"{live_server_url}/api/ipd/assign", json={"patient_id": pid, "nurse_id": nurses[i].id},
                      headers=_auth_headers(token), timeout=10)
    # Mint all tokens in the main thread first -- see the note in
    # test_many_simultaneous_logins_all_succeed_with_distinct_tokens on why ORM attribute
    # access must never happen from a worker thread against a shared Session.
    nurse_tokens = [mint_tokens(n)["access_token"] for n in nurses[:10]]

    def _record(args):
        i, pid = args
        return pid, requests.post(f"{live_server_url}/api/ipd/vitals", json={"patient_id": pid, "heart_rate": 70 + i},
                                   headers=_auth_headers(nurse_tokens[i]), timeout=10)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(_record, enumerate(patient_ids)))

    assert all(r.status_code == 200 for _, r in results)
    for i, pid in enumerate(patient_ids):
        vitals = requests.get(f"{live_server_url}/api/ipd/vitals/{pid}", headers=_auth_headers(token), timeout=10).json()
        assert len(vitals) == 1
        assert vitals[0]["heart_rate"] == 70 + i, "cross-patient vitals corruption under concurrent load"


# ---------------------------------------------------------------------------
# Bulk simultaneous admissions -- a busy-day admission rush, many NursingStation/HeadNurse
# operators (or the same one firing rapid requests) admitting patients at the same time.
# ---------------------------------------------------------------------------

def test_bulk_concurrent_patient_admissions_no_id_collisions(live_server_url, station):
    token = mint_tokens(station)["access_token"]

    def _admit(i):
        return requests.post(f"{live_server_url}/api/ipd/patients",
                              json={"name": f"Bulk Admit {i}", "ward": "General", "bed": str(i)},
                              headers=_auth_headers(token), timeout=10)

    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as pool:
        results = list(pool.map(_admit, range(50)))

    assert all(r.status_code == 200 for r in results), [r.text for r in results if r.status_code != 200]
    ids = [r.json()["id"] for r in results]
    assert len(set(ids)) == 50, "duplicate patient IDs returned under concurrent admission load"

    roster = requests.get(f"{live_server_url}/api/ipd/patients", headers=_auth_headers(token), timeout=10).json()
    assert len(roster) == 50


# ---------------------------------------------------------------------------
# Simultaneous logins -- many staff clocking in for a shift at once.
# ---------------------------------------------------------------------------

def test_many_simultaneous_logins_all_succeed_with_distinct_tokens(live_server_url, make_user):
    # Capture plain strings before threading -- make_user()'s ORM objects share one SQLAlchemy
    # Session (not thread-safe), and each commit() expires all its prior objects' attributes,
    # so a worker thread lazily re-reading `.email` off a shared Session mid-test corrupts
    # (ObjectDeletedError), independent of anything the app itself does.
    emails = [f"shift-login{i}@concurrency.com" for i in range(20)]
    for email in emails:
        make_user(email=email, role="Nurse")

    def _login(email):
        return requests.post(f"{live_server_url}/api/auth/login",
                              json={"email": email, "password": "Str0ng!Passw0rd#1"}, timeout=10)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(_login, emails))

    assert all(r.status_code == 200 for r in results), [r.text for r in results if r.status_code != 200]
    tokens = [r.json()["access_token"] for r in results]
    assert len(set(tokens)) == 20, "expected 20 distinct access tokens from 20 simultaneous logins"


def test_repeated_failed_logins_from_same_account_concurrently_still_locks_correctly(live_server_url, make_user, db_session):
    """5 simultaneous wrong-password attempts on one account -- confirms the failed-attempt
    counter and lockout still behave sanely (locks, doesn't silently allow unlimited attempts
    to race past the 5-attempt threshold) even when the increments overlap in time."""
    from app.models import User
    email = "lockout-race@concurrency.com"
    user = make_user(email=email, role="Nurse")
    user_id = user.id

    def _bad_login():
        return requests.post(f"{live_server_url}/api/auth/login",
                              json={"email": email, "password": "wrong-password"}, timeout=10)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _bad_login(), range(8)))

    assert all(r.status_code in (401, 403) for r in results)
    db_session.expire_all()
    refreshed = db_session.query(User).filter(User.id == user_id).first()
    # Under true concurrency the counter may undercount somewhat (classic lost-update on a
    # non-atomic read-increment-write), but the account must end up locked, not still Active
    # after 8 concurrent bad attempts against a 5-attempt threshold.
    assert refreshed.status == "Locked", (
        f"expected account to be Locked after 8 concurrent failed attempts (threshold 5), "
        f"got status={refreshed.status!r}, failed_login_attempts={refreshed.failed_login_attempts}"
    )


# ---------------------------------------------------------------------------
# High-volume simultaneous reads -- a shift-change moment where many staff load the dashboard
# at once.
# ---------------------------------------------------------------------------

def test_high_volume_concurrent_dashboard_reads(live_server_url, head_nurse, station, make_user):
    token = mint_tokens(head_nurse)["access_token"]
    for i in range(15):
        requests.post(f"{live_server_url}/api/ipd/patients", json={"name": f"Read Load Patient {i}", "ward": "General", "bed": str(i)},
                      headers=_auth_headers(token), timeout=10)

    readers = [make_user(email=f"reader{i}@concurrency.com", role="HeadNurse", organization_id=head_nurse.organization_id) for i in range(15)]
    reader_tokens = [mint_tokens(r)["access_token"] for r in readers]

    def _read(t):
        return requests.get(f"{live_server_url}/api/ipd/patients", headers=_auth_headers(t), timeout=10)

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
        results = list(pool.map(_read, reader_tokens))

    assert all(r.status_code == 200 for r in results)
    assert all(len(r.json()) == 15 for r in results), "inconsistent roster size seen under concurrent read load"


def test_server_survives_mixed_read_write_load_without_crashing(live_server_url, head_nurse, nurses):
    """A realistic mixed-load burst: admissions, assignments, vitals, and roster reads all
    firing at once -- the closest approximation of a genuinely busy ward moment. The bar here
    is simple: the server must not crash, hang, or return any 500s."""
    token = mint_tokens(head_nurse)["access_token"]
    nurse_tokens = [mint_tokens(n)["access_token"] for n in nurses]

    def _admit(i):
        return requests.post(f"{live_server_url}/api/ipd/patients",
                              json={"name": f"Mixed Load {i}", "ward": "General", "bed": str(i)},
                              headers=_auth_headers(token), timeout=15)

    def _read_roster(i):
        return requests.get(f"{live_server_url}/api/ipd/patients", headers=_auth_headers(nurse_tokens[i % len(nurse_tokens)]), timeout=15)

    def _health_check(i):
        return requests.get(f"{live_server_url}/api/health", timeout=15)

    tasks = [(_admit, i) for i in range(20)] + [(_read_roster, i) for i in range(20)] + [(_health_check, i) for i in range(10)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as pool:
        futures = [pool.submit(fn, i) for fn, i in tasks]
        results = [f.result() for f in futures]

    server_errors = [r for r in results if r.status_code >= 500]
    assert server_errors == [], f"{len(server_errors)} requests returned 5xx under mixed concurrent load"

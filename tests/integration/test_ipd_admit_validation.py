"""
POST /api/ipd/patients validation added alongside the Ward model: duplicate-name confirmation
gate, age range, ward-capacity enforcement (skipped when no Ward row is configured, so admission
keeps working for orgs that haven't set up wards), and same-ward same-bed conflict detection.
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@admit-validation.com", role="HeadNurse")


@pytest.fixture
def station(make_user, head_nurse):
    return make_user(email="station@admit-validation.com", role="NursingStation", organization_id=head_nurse.organization_id)


def test_duplicate_name_blocked_without_confirmation(client, head_nurse, auth_headers):
    client.post("/api/ipd/patients", json={"name": "Alice", "ward": "General", "bed": "1"}, headers=auth_headers(head_nurse))
    resp = client.post("/api/ipd/patients", json={"name": "alice", "ward": "General", "bed": "2"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 409


def test_duplicate_name_proceeds_with_confirm_flag(client, head_nurse, auth_headers):
    client.post("/api/ipd/patients", json={"name": "Alice", "ward": "General", "bed": "1"}, headers=auth_headers(head_nurse))
    resp = client.post("/api/ipd/patients", json={"name": "Alice", "ward": "General", "bed": "2", "confirm_duplicate": True},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_duplicate_name_check_ignores_discharged_patients(client, head_nurse, auth_headers):
    pid = client.post("/api/ipd/patients", json={"name": "Alice", "ward": "General", "bed": "1"},
                       headers=auth_headers(head_nurse)).json()["id"]
    client.put(f"/api/patients/{pid}", json={"status": "Discharged"}, headers=auth_headers(head_nurse))
    resp = client.post("/api/ipd/patients", json={"name": "Alice", "ward": "General", "bed": "2"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


@pytest.mark.parametrize("age", [-1, 131, 500])
def test_invalid_age_rejected(client, head_nurse, auth_headers, age):
    resp = client.post("/api/ipd/patients", json={"name": "Bad Age", "ward": "General", "age": age},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 400


@pytest.mark.parametrize("age", [0, 1, 45, 130])
def test_valid_age_boundaries_accepted(client, head_nurse, auth_headers, age):
    """age=0 is a legitimate newborn (under 1 year), not an invalid value."""
    resp = client.post("/api/ipd/patients", json={"name": f"Good Age {age}", "ward": "General", "age": age},
                        headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_age_optional(client, head_nurse, auth_headers):
    resp = client.post("/api/ipd/patients", json={"name": "No Age Given", "ward": "General"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_ward_capacity_blocks_admission_once_full(client, head_nurse, auth_headers):
    client.post("/api/wards", json={"name": "ICU", "bed_capacity": 1}, headers=auth_headers(head_nurse))
    resp1 = client.post("/api/ipd/patients", json={"name": "First", "ward": "ICU", "bed": "1"}, headers=auth_headers(head_nurse))
    assert resp1.status_code == 200
    resp2 = client.post("/api/ipd/patients", json={"name": "Second", "ward": "ICU", "bed": "2"}, headers=auth_headers(head_nurse))
    assert resp2.status_code == 400


def test_ward_capacity_check_skipped_when_no_ward_configured(client, head_nurse, auth_headers):
    """Orgs that haven't set up Ward rows yet must keep admitting normally -- no backfill required."""
    for i in range(5):
        resp = client.post("/api/ipd/patients", json={"name": f"Patient {i}", "ward": "Unconfigured Ward", "bed": f"B{i}"},
                            headers=auth_headers(head_nurse))
        assert resp.status_code == 200


def test_ward_capacity_matches_case_insensitively(client, head_nurse, auth_headers):
    client.post("/api/wards", json={"name": "ICU", "bed_capacity": 1}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/patients", json={"name": "First", "ward": "icu", "bed": "1"}, headers=auth_headers(head_nurse))
    resp = client.post("/api/ipd/patients", json={"name": "Second", "ward": "ICU", "bed": "2"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_same_ward_same_bed_conflict_rejected(client, head_nurse, auth_headers):
    client.post("/api/ipd/patients", json={"name": "First", "ward": "General", "bed": "B1"}, headers=auth_headers(head_nurse))
    resp = client.post("/api/ipd/patients", json={"name": "Second", "ward": "General", "bed": "b1"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_same_bed_different_ward_is_fine(client, head_nurse, auth_headers):
    client.post("/api/ipd/patients", json={"name": "First", "ward": "ICU", "bed": "1"}, headers=auth_headers(head_nurse))
    resp = client.post("/api/ipd/patients", json={"name": "Second", "ward": "General", "bed": "1"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_bed_conflict_ignores_discharged_patients(client, head_nurse, auth_headers):
    pid = client.post("/api/ipd/patients", json={"name": "First", "ward": "General", "bed": "B1"},
                       headers=auth_headers(head_nurse)).json()["id"]
    client.put(f"/api/patients/{pid}", json={"status": "Discharged"}, headers=auth_headers(head_nurse))
    resp = client.post("/api/ipd/patients", json={"name": "Second", "ward": "General", "bed": "B1"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200


def test_nursing_station_subject_to_same_validation(client, station, head_nurse, auth_headers):
    client.post("/api/ipd/patients", json={"name": "Existing", "ward": "General", "bed": "1"}, headers=auth_headers(head_nurse))
    resp = client.post("/api/ipd/patients", json={"name": "existing", "ward": "General", "bed": "2"}, headers=auth_headers(station))
    assert resp.status_code == 409


def test_validation_scoped_per_organization(client, head_nurse, make_user, auth_headers):
    """A duplicate name / bed conflict in one org must not block admission of the same name/bed
    combination in a different org."""
    other_head_nurse = make_user(email="head@other-admit-validation.com", role="HeadNurse")
    client.post("/api/ipd/patients", json={"name": "Alice", "ward": "General", "bed": "1"}, headers=auth_headers(head_nurse))
    resp = client.post("/api/ipd/patients", json={"name": "Alice", "ward": "General", "bed": "1"}, headers=auth_headers(other_head_nurse))
    assert resp.status_code == 200

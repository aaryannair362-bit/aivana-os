"""
GET/POST/PATCH/DELETE /api/wards -- per-organization bed-capacity configuration, matched
case-insensitively against the existing free-text Patient.ward field. Covers CRUD happy path,
role gating (HeadNurse or Admin only), duplicate-name rejection, bed_capacity validation,
occupancy computation, delete-while-occupied blocking, and cross-org isolation.
"""
import pytest


@pytest.fixture
def head_nurse(make_user):
    return make_user(email="head@ward-mgmt.com", role="HeadNurse")


@pytest.fixture
def admin(make_user, head_nurse):
    return make_user(email="admin@ward-mgmt.com", role="Admin", organization_id=head_nurse.organization_id)


@pytest.fixture
def nurse(make_user, head_nurse):
    return make_user(email="nurse@ward-mgmt.com", role="Nurse", organization_id=head_nurse.organization_id)


@pytest.fixture
def other_org_head_nurse(make_user):
    return make_user(email="head@other-ward-mgmt.com", role="HeadNurse")


def test_head_nurse_can_create_and_list_ward(client, head_nurse, auth_headers):
    resp = client.post("/api/wards", json={"name": "ICU", "bed_capacity": 10}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "ICU"
    assert body["bed_capacity"] == 10
    assert body["occupied"] == 0

    listing = client.get("/api/wards", headers=auth_headers(head_nurse)).json()
    assert len(listing) == 1
    assert listing[0]["name"] == "ICU"


def test_admin_can_also_manage_wards(client, admin, auth_headers):
    resp = client.post("/api/wards", json={"name": "General", "bed_capacity": 20}, headers=auth_headers(admin))
    assert resp.status_code == 200


def test_nurse_cannot_manage_wards(client, nurse, auth_headers):
    resp = client.get("/api/wards", headers=auth_headers(nurse))
    assert resp.status_code == 403
    resp = client.post("/api/wards", json={"name": "ICU", "bed_capacity": 10}, headers=auth_headers(nurse))
    assert resp.status_code == 403


def test_duplicate_ward_name_case_insensitive_rejected(client, head_nurse, auth_headers):
    client.post("/api/wards", json={"name": "ICU", "bed_capacity": 10}, headers=auth_headers(head_nurse))
    resp = client.post("/api/wards", json={"name": "icu", "bed_capacity": 5}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


@pytest.mark.parametrize("bad_capacity", [0, -5, 1.5, "10", True, None])
def test_invalid_bed_capacity_rejected(client, head_nurse, auth_headers, bad_capacity):
    resp = client.post("/api/wards", json={"name": "ICU", "bed_capacity": bad_capacity}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_blank_ward_name_rejected(client, head_nurse, auth_headers):
    resp = client.post("/api/wards", json={"name": "   ", "bed_capacity": 10}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_occupancy_reflects_active_patients_case_insensitively(client, head_nurse, auth_headers):
    client.post("/api/wards", json={"name": "ICU", "bed_capacity": 5}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/patients", json={"name": "P1", "ward": "icu", "bed": "1"}, headers=auth_headers(head_nurse))
    client.post("/api/ipd/patients", json={"name": "P2", "ward": "ICU", "bed": "2"}, headers=auth_headers(head_nurse))
    listing = client.get("/api/wards", headers=auth_headers(head_nurse)).json()
    assert listing[0]["occupied"] == 2


def test_update_ward_capacity(client, head_nurse, auth_headers):
    ward_id = client.post("/api/wards", json={"name": "ICU", "bed_capacity": 10}, headers=auth_headers(head_nurse)).json()["id"]
    resp = client.patch(f"/api/wards/{ward_id}", json={"bed_capacity": 15}, headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    listing = client.get("/api/wards", headers=auth_headers(head_nurse)).json()
    assert listing[0]["bed_capacity"] == 15


def test_update_ward_name_rejects_duplicate(client, head_nurse, auth_headers):
    client.post("/api/wards", json={"name": "ICU", "bed_capacity": 10}, headers=auth_headers(head_nurse))
    ward2_id = client.post("/api/wards", json={"name": "General", "bed_capacity": 20}, headers=auth_headers(head_nurse)).json()["id"]
    resp = client.patch(f"/api/wards/{ward2_id}", json={"name": "icu"}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_update_ward_invalid_capacity_rejected(client, head_nurse, auth_headers):
    ward_id = client.post("/api/wards", json={"name": "ICU", "bed_capacity": 10}, headers=auth_headers(head_nurse)).json()["id"]
    resp = client.patch(f"/api/wards/{ward_id}", json={"bed_capacity": -1}, headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_update_nonexistent_ward_404(client, head_nurse, auth_headers):
    resp = client.patch("/api/wards/999999", json={"bed_capacity": 5}, headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_delete_empty_ward_succeeds(client, head_nurse, auth_headers):
    ward_id = client.post("/api/wards", json={"name": "ICU", "bed_capacity": 10}, headers=auth_headers(head_nurse)).json()["id"]
    resp = client.delete(f"/api/wards/{ward_id}", headers=auth_headers(head_nurse))
    assert resp.status_code == 200
    assert client.get("/api/wards", headers=auth_headers(head_nurse)).json() == []


def test_delete_occupied_ward_blocked(client, head_nurse, auth_headers):
    ward_id = client.post("/api/wards", json={"name": "ICU", "bed_capacity": 10}, headers=auth_headers(head_nurse)).json()["id"]
    client.post("/api/ipd/patients", json={"name": "P1", "ward": "ICU", "bed": "1"}, headers=auth_headers(head_nurse))
    resp = client.delete(f"/api/wards/{ward_id}", headers=auth_headers(head_nurse))
    assert resp.status_code == 400


def test_delete_nonexistent_ward_404(client, head_nurse, auth_headers):
    resp = client.delete("/api/wards/999999", headers=auth_headers(head_nurse))
    assert resp.status_code == 404


def test_wards_are_isolated_per_organization(client, head_nurse, other_org_head_nurse, auth_headers):
    client.post("/api/wards", json={"name": "ICU", "bed_capacity": 10}, headers=auth_headers(head_nurse))
    other_listing = client.get("/api/wards", headers=auth_headers(other_org_head_nurse)).json()
    assert other_listing == []


def test_cannot_patch_or_delete_another_orgs_ward(client, head_nurse, other_org_head_nurse, auth_headers):
    ward_id = client.post("/api/wards", json={"name": "ICU", "bed_capacity": 10}, headers=auth_headers(head_nurse)).json()["id"]
    resp = client.patch(f"/api/wards/{ward_id}", json={"bed_capacity": 99}, headers=auth_headers(other_org_head_nurse))
    assert resp.status_code == 404
    resp = client.delete(f"/api/wards/{ward_id}", headers=auth_headers(other_org_head_nurse))
    assert resp.status_code == 404

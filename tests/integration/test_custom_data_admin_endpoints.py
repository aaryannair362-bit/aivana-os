"""
Tests for the admin-only custom-medicine / custom-lab-test management endpoints
(POST/GET/DELETE /api/admin/medicines, /api/admin/lab-tests). These let an Admin add an entry
missing from the bundled datasets (drug_matcher.py's ~249k medicines, lab_test_matcher.py's 195
lab tests) without hand-editing the large source files, and the new entry must be matchable
immediately (cache invalidation), not just listable.

Every test monkeypatches each matcher's CUSTOM_DATA_PATH to a tmp_path file rather than using
the real backend/app/data/custom_*.csv -- those are real, shared, version-controlled-adjacent
files the actual running app reads, and a test suite must never write throwaway entries into
them (no per-test DB-style isolation exists for these plain CSV files otherwise).
"""
import pytest

from app import drug_matcher, lab_test_matcher


@pytest.fixture(autouse=True)
def _isolated_custom_data_files(tmp_path, monkeypatch):
    med_path = tmp_path / "custom_medicines.csv"
    lab_path = tmp_path / "custom_lab_tests.csv"
    monkeypatch.setattr(drug_matcher, "CUSTOM_DATA_PATH", med_path)
    monkeypatch.setattr(lab_test_matcher, "CUSTOM_DATA_PATH", lab_path)
    drug_matcher.invalidate_cache()
    lab_test_matcher.invalidate_cache()
    yield
    drug_matcher.invalidate_cache()
    lab_test_matcher.invalidate_cache()


@pytest.fixture
def admin(make_user):
    return make_user(email="admin@custom-data.com", role="Admin")


@pytest.fixture
def doctor(make_user, admin):
    return make_user(email="doctor@custom-data.com", role="Doctor", organization_id=admin.organization_id)


class TestCustomMedicineEndpoints:
    def test_admin_can_add_list_and_delete_a_medicine(self, client, admin, auth_headers):
        headers = auth_headers(admin)
        assert client.get("/api/admin/medicines", headers=headers).json() == []

        resp = client.post("/api/admin/medicines", json={"name": "Tablet Wondermed 500"}, headers=headers)
        assert resp.status_code == 200
        entry = resp.json()
        assert entry["name"] == "Tablet Wondermed 500"
        assert entry["added_by"] == admin.email

        listed = client.get("/api/admin/medicines", headers=headers).json()
        assert len(listed) == 1
        assert listed[0]["name"] == "Tablet Wondermed 500"

        resp = client.delete(f"/api/admin/medicines/{entry['id']}", headers=headers)
        assert resp.status_code == 200
        assert client.get("/api/admin/medicines", headers=headers).json() == []

    def test_added_medicine_is_matchable_immediately(self, client, admin, auth_headers):
        headers = auth_headers(admin)
        assert drug_matcher.closest_medicine_name("Tablet Wondermed") is None
        client.post("/api/admin/medicines", json={"name": "Wondermed 500 Tablet"}, headers=headers)
        # No server restart, no manual reload -- the very next lookup in this process must see it.
        assert drug_matcher.closest_medicine_name("Tablet Wondermed") == "Wondermed 500 Tablet"

    def test_duplicate_name_is_rejected(self, client, admin, auth_headers):
        headers = auth_headers(admin)
        client.post("/api/admin/medicines", json={"name": "Tablet Duplimed 100"}, headers=headers)
        resp = client.post("/api/admin/medicines", json={"name": "tablet duplimed 100"}, headers=headers)
        assert resp.status_code == 400

    def test_blank_name_is_rejected(self, client, admin, auth_headers):
        resp = client.post("/api/admin/medicines", json={"name": "   "}, headers=auth_headers(admin))
        assert resp.status_code == 400

    def test_deleting_nonexistent_entry_404s(self, client, admin, auth_headers):
        resp = client.delete("/api/admin/medicines/99999", headers=auth_headers(admin))
        assert resp.status_code == 404

    def test_non_admin_roles_are_denied(self, client, doctor, auth_headers):
        headers = auth_headers(doctor)
        assert client.get("/api/admin/medicines", headers=headers).status_code == 403
        assert client.post("/api/admin/medicines", json={"name": "X"}, headers=headers).status_code == 403
        assert client.delete("/api/admin/medicines/1", headers=headers).status_code == 403

    def test_unauthenticated_request_is_denied(self, client):
        assert client.get("/api/admin/medicines").status_code in (401, 403)


class TestCustomLabTestEndpoints:
    def test_admin_can_add_list_and_delete_a_lab_test(self, client, admin, auth_headers):
        headers = auth_headers(admin)
        assert client.get("/api/admin/lab-tests", headers=headers).json() == []

        resp = client.post("/api/admin/lab-tests", json={
            "test_name": "Novel Biomarker Panel", "common_alias": "NBP",
            "department": "Biochemistry", "specimen": "Serum",
        }, headers=headers)
        assert resp.status_code == 200
        entry = resp.json()
        assert entry["test_name"] == "Novel Biomarker Panel"
        assert entry["common_alias"] == "NBP"
        assert entry["added_by"] == admin.email

        listed = client.get("/api/admin/lab-tests", headers=headers).json()
        assert len(listed) == 1

        resp = client.delete(f"/api/admin/lab-tests/{entry['id']}", headers=headers)
        assert resp.status_code == 200
        assert client.get("/api/admin/lab-tests", headers=headers).json() == []

    def test_added_lab_test_and_its_alias_are_matchable_immediately(self, client, admin, auth_headers):
        headers = auth_headers(admin)
        assert lab_test_matcher.closest_lab_test_name("NBP") is None
        client.post("/api/admin/lab-tests", json={
            "test_name": "Novel Biomarker Panel", "common_alias": "NBP",
        }, headers=headers)
        assert lab_test_matcher.closest_lab_test_name("NBP") == "Novel Biomarker Panel"
        assert lab_test_matcher.closest_lab_test_name("Novel Biomarker Panel") == "Novel Biomarker Panel"

    def test_optional_fields_default_to_empty(self, client, admin, auth_headers):
        resp = client.post("/api/admin/lab-tests", json={"test_name": "Minimal Test"}, headers=auth_headers(admin))
        entry = resp.json()
        assert entry["common_alias"] == ""
        assert entry["department"] == ""
        assert entry["specimen"] == ""

    def test_duplicate_test_name_is_rejected(self, client, admin, auth_headers):
        headers = auth_headers(admin)
        client.post("/api/admin/lab-tests", json={"test_name": "Duplicate Panel"}, headers=headers)
        resp = client.post("/api/admin/lab-tests", json={"test_name": "duplicate panel"}, headers=headers)
        assert resp.status_code == 400

    def test_blank_test_name_is_rejected(self, client, admin, auth_headers):
        resp = client.post("/api/admin/lab-tests", json={"test_name": ""}, headers=auth_headers(admin))
        assert resp.status_code == 400

    def test_deleting_nonexistent_entry_404s(self, client, admin, auth_headers):
        resp = client.delete("/api/admin/lab-tests/99999", headers=auth_headers(admin))
        assert resp.status_code == 404

    def test_non_admin_roles_are_denied(self, client, doctor, auth_headers):
        headers = auth_headers(doctor)
        assert client.get("/api/admin/lab-tests", headers=headers).status_code == 403
        assert client.post("/api/admin/lab-tests", json={"test_name": "X"}, headers=headers).status_code == 403
        assert client.delete("/api/admin/lab-tests/1", headers=headers).status_code == 403

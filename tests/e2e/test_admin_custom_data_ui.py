"""
Real-browser regression test for the "Medicine List" / "Lab Test List" management UI added to
frontend/admin.html: an Admin adds a custom medicine/lab test through the actual form (not a
raw API call), sees it appear in the table immediately, then removes it.

Isolated from the real backend/app/data/custom_*.csv files the same way
tests/integration/test_custom_data_admin_endpoints.py is -- these are real, shared, plain-file
"databases" with no per-test reset otherwise.
"""
import pytest

from tests._voice_helpers import mint_tokens, set_tokens_in_browser

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def _isolated_custom_data_files(tmp_path, monkeypatch):
    import app.drug_matcher as drug_matcher
    import app.lab_test_matcher as lab_test_matcher

    monkeypatch.setattr(drug_matcher, "CUSTOM_DATA_PATH", tmp_path / "custom_medicines.csv")
    monkeypatch.setattr(lab_test_matcher, "CUSTOM_DATA_PATH", tmp_path / "custom_lab_tests.csv")
    drug_matcher.invalidate_cache()
    lab_test_matcher.invalidate_cache()
    yield
    drug_matcher.invalidate_cache()
    lab_test_matcher.invalidate_cache()


@pytest.fixture
def admin(make_user):
    return make_user(email="admin@e2e-custom-data.com", role="Admin")


def test_admin_can_add_and_remove_a_custom_medicine_through_the_ui(js_page, live_server_url, admin):
    tokens = mint_tokens(admin)
    set_tokens_in_browser(js_page, live_server_url, tokens["access_token"], tokens["refresh_token"])

    js_page.goto(f"{live_server_url}/admin.html")
    js_page.wait_for_selector("#new-medicine-name")
    js_page.fill("#new-medicine-name", "Tablet E2E Testonin 100")
    js_page.click("#add-medicine-btn")
    js_page.wait_for_function(
        "document.getElementById('medicine-table-body').textContent.includes('Tablet E2E Testonin 100')",
        timeout=10000,
    )

    row_text = js_page.eval_on_selector("#medicine-table-body", "el => el.textContent")
    assert "Tablet E2E Testonin 100" in row_text
    assert admin.email in row_text

    js_page.click("#medicine-table-body .delete-medicine")
    js_page.wait_for_function(
        "!document.getElementById('medicine-table-body').textContent.includes('Tablet E2E Testonin 100')",
        timeout=10000,
    )
    assert js_page.js_errors == [], f"unexpected JS errors: {js_page.js_errors}"


def test_admin_can_add_and_remove_a_custom_lab_test_through_the_ui(js_page, live_server_url, admin):
    tokens = mint_tokens(admin)
    set_tokens_in_browser(js_page, live_server_url, tokens["access_token"], tokens["refresh_token"])

    js_page.goto(f"{live_server_url}/admin.html")
    js_page.wait_for_selector("#new-lab-test-name")
    js_page.fill("#new-lab-test-name", "E2E Novel Marker Test")
    js_page.fill("#new-lab-test-alias", "ENMT")
    js_page.click("#add-lab-test-btn")
    js_page.wait_for_function(
        "document.getElementById('lab-test-table-body').textContent.includes('E2E Novel Marker Test')",
        timeout=10000,
    )

    row_text = js_page.eval_on_selector("#lab-test-table-body", "el => el.textContent")
    assert "E2E Novel Marker Test" in row_text
    assert "ENMT" in row_text

    js_page.click("#lab-test-table-body .delete-lab-test")
    js_page.wait_for_function(
        "!document.getElementById('lab-test-table-body').textContent.includes('E2E Novel Marker Test')",
        timeout=10000,
    )
    assert js_page.js_errors == [], f"unexpected JS errors: {js_page.js_errors}"

"""
Integration tests — dashboard API.
Seam: GET /api/dashboard/ (DashboardAPIView)
"""
import requests

from constants import APP_HOST, BASE_URL


def test_dashboard_api_returns_200(manager_session):
    r = manager_session.get(f"{BASE_URL}/api/dashboard/")
    assert r.status_code == 200, r.text


def test_dashboard_api_has_kpi_fields(manager_session):
    data = manager_session.get(f"{BASE_URL}/api/dashboard/").json()
    assert data.get("success") is True, data
    response = data.get("response", {})
    for key in (
        "total_claims",
        "pending_claims",
        "denial_rate",
        "pending_revenue",
        "pending_ai_tasks",
    ):
        assert key in response, f"Missing key '{key}' in dashboard response: {response}"


def test_dashboard_pending_ai_tasks_is_nonnegative(manager_session):
    data = manager_session.get(f"{BASE_URL}/api/dashboard/").json()
    pending_ai_tasks = data.get("response", {}).get("pending_ai_tasks", -1)
    assert pending_ai_tasks >= 0, f"pending_ai_tasks must be >= 0, got {pending_ai_tasks}"


def test_dashboard_recent_claims_is_list(manager_session):
    data = manager_session.get(f"{BASE_URL}/api/dashboard/").json()
    recent = data.get("response", {}).get("recent_claims")
    assert isinstance(recent, list), f"recent_claims should be a list, got: {type(recent)}"


def test_dashboard_total_claims_is_nonnegative(manager_session):
    data = manager_session.get(f"{BASE_URL}/api/dashboard/").json()
    total = data.get("response", {}).get("total_claims", -1)
    assert total >= 0, f"total_claims must be >= 0, got {total}"


def test_dashboard_anonymous_is_blocked():
    """Anonymous users must not receive dashboard PHI data — expect redirect to login or 403."""
    s = requests.Session()
    s.headers.update({"Host": APP_HOST})
    r = s.get(f"{BASE_URL}/api/dashboard/", allow_redirects=False)
    assert r.status_code in (302, 401, 403), (
        f"Expected redirect or auth error for anonymous user, got {r.status_code}"
    )


def test_dashboard_staff_returns_403(app_session):
    r = app_session.get(f"{BASE_URL}/api/dashboard/")
    assert r.status_code == 403, f"Expected 403 for BillingStaff, got {r.status_code}"

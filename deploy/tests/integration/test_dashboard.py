"""
Integration tests — dashboard API.
Seam: GET /api/dashboard/ (DashboardAPIView)
"""
from constants import BASE_URL


def test_dashboard_api_returns_200(app_session):
    r = app_session.get(f"{BASE_URL}/api/dashboard/")
    assert r.status_code == 200, r.text


def test_dashboard_api_has_kpi_fields(app_session):
    data = app_session.get(f"{BASE_URL}/api/dashboard/").json()
    assert data.get("success") is True, data
    response = data.get("response", {})
    for key in ("total_claims", "pending_claims", "denial_rate", "pending_revenue"):
        assert key in response, f"Missing key '{key}' in dashboard response: {response}"


def test_dashboard_recent_claims_is_list(app_session):
    data = app_session.get(f"{BASE_URL}/api/dashboard/").json()
    recent = data.get("response", {}).get("recent_claims")
    assert isinstance(recent, list), f"recent_claims should be a list, got: {type(recent)}"


def test_dashboard_total_claims_is_nonnegative(app_session):
    data = app_session.get(f"{BASE_URL}/api/dashboard/").json()
    total = data.get("response", {}).get("total_claims", -1)
    assert total >= 0, f"total_claims must be >= 0, got {total}"

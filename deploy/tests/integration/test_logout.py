"""Integration coverage for the deployed frontend's logout endpoint."""

import pytest
import requests

from constants import APP_HOST, BASE_URL, STAFF_EMAIL, STAFF_PASS


@pytest.fixture(scope="session")
def logout_session():
    """A dedicated authenticated session so logout cannot affect other tests."""
    session = requests.Session()
    session.headers.update({"Host": APP_HOST})

    session.get(f"{BASE_URL}/api/v1/appauth/login/")
    csrf = session.cookies.get("csrftoken") or ""
    response = session.post(
        f"{BASE_URL}/api/v1/appauth/login/",
        headers={"X-CSRFToken": csrf},
        json={"email": STAFF_EMAIL, "password": STAFF_PASS},
    )
    assert response.status_code == 200, response.text
    assert response.json().get("success") is True, response.text
    return session


def test_frontend_logout_endpoint_accepts_post_without_trailing_slash(logout_session):
    csrf = logout_session.cookies.get("csrftoken") or ""

    response = logout_session.post(
        f"{BASE_URL}/api/auth/logout",
        headers={"X-CSRFToken": csrf},
    )

    assert response.status_code == 204, response.text

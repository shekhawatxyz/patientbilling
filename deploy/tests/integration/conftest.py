"""
Integration test fixtures.

All tests in this suite run against the live Docker stack on localhost:8000.
The app uses a Host header to route to the patientbilling tenant.
"""
import time

import pytest
import requests

from constants import (
    APP_HOST, APP_UUID, BASE_URL,
    PLATFORM_PASS, PLATFORM_USER,
    STAFF_EMAIL, STAFF_PASS,
)


@pytest.fixture(scope="session")
def app_session():
    """Authenticated requests.Session for the patientbilling app (staff role)."""
    s = requests.Session()
    s.headers.update({"Host": APP_HOST})

    # Fetch CSRF token
    s.get(f"{BASE_URL}/api/v1/appauth/login/")
    csrf: str = s.cookies.get("csrftoken") or ""

    # Attempt login
    resp = s.post(
        f"{BASE_URL}/api/v1/appauth/login/",
        headers={"X-CSRFToken": csrf},
        json={"email": STAFF_EMAIL, "password": STAFF_PASS},
    )
    body = resp.json()

    # Handle first-login set-password flow
    if (
        body.get("response", {})
            .get("data", {})
            .get("next_step", {})
            .get("id") == "set_password"
    ):
        csrf = s.cookies.get("csrftoken") or ""
        s.post(
            f"{BASE_URL}/api/v1/appauth/password/set/",
            headers={"X-CSRFToken": csrf},
            json={"new_password": STAFF_PASS, "confirm_password": STAFF_PASS},
        )

    return s


@pytest.fixture(scope="session")
def platform_session():
    """Authenticated requests.Session for the platform admin panel."""
    s = requests.Session()

    r = s.get(f"{BASE_URL}/auth/login/")
    import re
    match = re.search(r'csrfmiddlewaretoken" value="([^"]+)"', r.text)
    csrf = match.group(1) if match else ""

    s.post(
        f"{BASE_URL}/auth/login/",
        headers={"X-CSRFToken": csrf, "Referer": f"{BASE_URL}/auth/login/"},
        data={
            "username": PLATFORM_USER,
            "password": PLATFORM_PASS,
            "csrfmiddlewaretoken": csrf,
        },
    )
    return s


@pytest.fixture(scope="session")
def run_id():
    """Short unique suffix for idempotent test data (avoids collisions across runs)."""
    return str(int(time.time()))[-6:]

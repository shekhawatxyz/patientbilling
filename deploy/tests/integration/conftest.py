"""
Integration test fixtures.

All tests in this suite run against the live Docker stack on localhost:8000.
The app uses a Host header to route to the patientbilling tenant.
"""
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from constants import (
    APP_HOST, APP_UUID, BASE_URL,
    MANAGER_EMAIL, MANAGER_PASS,
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
def manager_session():
    """Authenticated requests.Session for the patientbilling app (manager role)."""
    s = requests.Session()
    s.headers.update({"Host": APP_HOST})

    s.get(f"{BASE_URL}/api/v1/appauth/login/")
    csrf: str = s.cookies.get("csrftoken") or ""

    resp = s.post(
        f"{BASE_URL}/api/v1/appauth/login/",
        headers={"X-CSRFToken": csrf},
        json={"email": MANAGER_EMAIL, "password": MANAGER_PASS},
    )
    body = resp.json()

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
            json={"new_password": MANAGER_PASS, "confirm_password": MANAGER_PASS},
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


@pytest.fixture(scope="session", autouse=True)
def cleanup_session_test_data():
    """Delete only test-prefix rows created during this live HTTP test session."""
    session_start = datetime.now(timezone.utc).isoformat()
    yield

    container_manage = Path("/zango/zango_project/manage.py")
    if container_manage.exists():
        subprocess.run(
            [
                sys.executable,
                str(container_manage),
                "cleanup_test_data",
                "--execute",
                "--created-since",
                session_start,
            ],
            cwd=container_manage.parent,
            check=True,
        )
        return

    repo_root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(repo_root / "docker_compose.yml"),
            "exec",
            "-T",
            "app",
            "sh",
            "-c",
            f"cd zango_project && python manage.py cleanup_test_data --execute --created-since {session_start}",
        ],
        cwd=repo_root,
        check=True,
    )

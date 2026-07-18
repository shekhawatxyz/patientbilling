"""Authentication rejection smoke tests."""
import requests

from constants import APP_HOST, BASE_URL, MANAGER_EMAIL, STAFF_EMAIL


def test_wrong_password_rejected_for_staff_and_manager():
    for email in (STAFF_EMAIL, MANAGER_EMAIL):
        session = requests.Session()
        session.headers.update({"Host": APP_HOST})
        session.get(f"{BASE_URL}/api/v1/appauth/login/")
        csrf = session.cookies.get("csrftoken") or ""
        response = session.post(f"{BASE_URL}/api/v1/appauth/login/", headers={"X-CSRFToken": csrf}, json={"email": email, "password": "definitely-wrong"})
        assert response.status_code in (400, 401, 403), response.text
        assert response.json().get("success") is not True, response.text

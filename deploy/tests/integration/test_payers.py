"""Integration tests — payers module CRUD."""
from constants import BASE_URL


def _rows(session):
    response = session.get(f"{BASE_URL}/payers/", params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 200})
    assert response.status_code == 200, response.text
    return response.json().get("data", [])


def _create(session, suffix):
    csrf = session.cookies.get("csrftoken") or ""
    response = session.post(f"{BASE_URL}/payers/", headers={"X-CSRFToken": csrf}, params={"form_type": "create_form"}, data={"name": f"Payer {suffix}", "payer_id": f"PAY-{suffix}", "contact_email": f"payer-{suffix}@test.com"})
    assert response.status_code == 200 and response.json().get("success") is True, response.text
    return response.json()["response"]["object_uuid"]


def test_payers_list_returns_200(app_session):
    assert _rows(app_session) is not None


def test_create_edit_and_delete_payer(app_session, run_id):
    object_uuid = _create(app_session, run_id)
    csrf = app_session.cookies.get("csrftoken") or ""
    response = app_session.post(f"{BASE_URL}/payers/", headers={"X-CSRFToken": csrf}, params={"action_type": "row", "action_key": "edit", "form_type": "row_action_form", "object_uuid": object_uuid}, data={"name": f"Edited Payer {run_id}", "payer_id": f"PAY-{run_id}", "contact_email": f"payer-{run_id}@test.com"})
    assert response.status_code == 200 and response.json().get("success") is True, response.text
    assert any(row.get("name") == f"Edited Payer {run_id}" for row in _rows(app_session))
    response = app_session.post(f"{BASE_URL}/payers/", headers={"X-CSRFToken": csrf}, params={"action_type": "row", "action_key": "delete", "object_uuid": object_uuid})
    assert response.status_code == 200 and response.json().get("success") is True, response.text
    assert not any(str(row.get("object_uuid")) == object_uuid for row in _rows(app_session))

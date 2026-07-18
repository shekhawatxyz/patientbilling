"""
Integration tests — patients module.
Seam: /patients/ HTTP endpoints (list, create, retrieve).
"""
from constants import BASE_URL


def test_patients_list_returns_200(app_session):
    r = app_session.get(
        f"{BASE_URL}/patients/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 10},
    )
    assert r.status_code == 200, r.text
    assert "data" in r.json()


def test_create_patient_succeeds(app_session, run_id):
    csrf = app_session.cookies.get("csrftoken", "")
    r = app_session.post(
        f"{BASE_URL}/patients/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "first_name": f"Test{run_id}",
            "last_name": "Patient",
            "date_of_birth": "1990-03-15",
            "email": f"pt{run_id}@test.com",
            "phone": "555-0100",
            "insurance_provider": "BCBS",
            "insurance_policy_number": f"POL-{run_id}",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True, body


def test_created_patient_appears_in_list(app_session, run_id):
    csrf = app_session.cookies.get("csrftoken", "")
    # Create
    app_session.post(
        f"{BASE_URL}/patients/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "first_name": f"Listed{run_id}",
            "last_name": "Person",
            "date_of_birth": "1985-06-20",
            "email": f"listed{run_id}@test.com",
        },
    )
    # Fetch list
    r = app_session.get(
        f"{BASE_URL}/patients/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 100},
    )
    names = [row.get("first_name", "") for row in r.json().get("data", [])]
    assert f"Listed{run_id}" in names, f"Patient not found in list: {names[:5]}"


def test_patient_create_form_returns_200(app_session):
    """Form GET serves the CRUD HTML shell (not JSON) — just verify it loads."""
    r = app_session.get(
        f"{BASE_URL}/patients/",
        params={"form_type": "create_form"},
    )
    assert r.status_code == 200, r.text
    assert "text/html" in r.headers.get("Content-Type", ""), (
        f"Expected HTML page, got: {r.headers.get('Content-Type')}"
    )


def _patient(session, run_id):
    csrf = session.cookies.get("csrftoken") or ""
    response = session.post(
        f"{BASE_URL}/patients/", headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={"first_name": f"Crud{run_id}", "last_name": "Patient",
              "date_of_birth": "1990-03-15", "email": f"crud{run_id}@test.com"},
    )
    assert response.json().get("success") is True, response.text
    return response.json()["response"]["object_uuid"]


def _patient_rows(session):
    response = session.get(
        f"{BASE_URL}/patients/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 200},
    )
    assert response.status_code == 200, response.text
    return response.json().get("data", [])


def test_staff_can_edit_patient_and_table_reflects_change(app_session, run_id):
    object_uuid = _patient(app_session, f"edit{run_id}")
    csrf = app_session.cookies.get("csrftoken") or ""
    response = app_session.post(
        f"{BASE_URL}/patients/", headers={"X-CSRFToken": csrf},
        params={"action_type": "row", "action_key": "edit", "form_type": "row_action_form", "object_uuid": object_uuid},
        data={"first_name": f"Edited{run_id}", "last_name": "Patient", "date_of_birth": "1990-03-15", "email": f"crud{run_id}@test.com"},
    )
    assert response.status_code == 200, response.text
    assert response.json().get("success") is True, response.text
    assert any(row.get("first_name") == f"Edited{run_id}" for row in _patient_rows(app_session))


def test_staff_can_delete_patient_and_table_excludes_it(app_session, run_id):
    object_uuid = _patient(app_session, f"delete{run_id}")
    csrf = app_session.cookies.get("csrftoken") or ""
    response = app_session.post(
        f"{BASE_URL}/patients/", headers={"X-CSRFToken": csrf},
        params={"action_type": "row", "action_key": "delete", "object_uuid": object_uuid},
    )
    assert response.status_code == 200, response.text
    assert response.json().get("success") is True, response.text
    assert not any(str(row.get("object_uuid")) == object_uuid for row in _patient_rows(app_session))

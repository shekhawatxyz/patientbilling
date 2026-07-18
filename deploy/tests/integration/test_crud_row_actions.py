"""Integration smoke tests for every configured CRUD row action."""
import pytest

from constants import BASE_URL


MODULE_ROW_ACTIONS = {
    "patients": ("edit",),
    "claims": ("edit",),
    "invoices": ("edit",),
    "payers": ("edit",),
}


def _create(session, module, suffix):
    csrf = session.cookies.get("csrftoken") or ""
    data = {
        "patients": {
            "first_name": f"RowAction{suffix}",
            "last_name": "Patient",
            "date_of_birth": "1985-01-01",
            "email": f"row-action-{suffix}@test.com",
        },
        "payers": {
            "name": f"Row Action Payer {suffix}",
            "payer_id": f"ROW-{suffix}",
            "contact_email": f"row-payer-{suffix}@test.com",
        },
    }

    if module == "invoices":
        patient = _create_reference(session, "patients", f"{suffix}-invoice-patient")
        data[module] = {
            "patient": patient,
            "invoice_number": f"ROW-INV-{suffix}",
            "date_issued": "2026-07-01",
            "due_date": "2026-07-31",
            "total_amount": "350.00",
        }
    elif module == "claims":
        patient = _create_reference(session, "patients", f"{suffix}-claim-patient")
        payer = _create_reference(session, "payers", f"{suffix}-claim-payer")
        data[module] = {
            "patient": patient,
            "payer": payer,
            "claim_number": f"ROW-CLM-{suffix}",
            "date_of_service": "2026-07-01",
            "diagnosis_codes": '["Z00.00"]',
            "total_amount": "500.00",
        }

    response = session.post(
        f"{BASE_URL}/{module}/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data=data[module],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("success") is True, body
    object_uuid = body.get("response", {}).get("object_uuid")
    assert object_uuid, f"Create response did not include object_uuid: {body}"
    return object_uuid


def _create_reference(session, module, suffix):
    object_uuid = _create(session, module, suffix)
    response = session.get(
        f"{BASE_URL}/{module}/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 200},
    )
    assert response.status_code == 200, response.text
    for row in response.json().get("data", []):
        if str(row.get("object_uuid")) == str(object_uuid):
            return row["pk"]
    raise AssertionError(f"Could not find {module} object {object_uuid} in table data")


@pytest.mark.parametrize("module,action_key", [
    (module, action_key)
    for module, action_keys in MODULE_ROW_ACTIONS.items()
    for action_key in action_keys
])
@pytest.mark.parametrize("session_fixture", ["app_session", "manager_session"])
def test_row_action_initialize_form_is_available(
    request, run_id, module, action_key, session_fixture
):
    session = request.getfixturevalue(session_fixture)
    object_uuid = _create(session, module, f"{run_id}-{module}-{session_fixture}")

    response = session.get(
        f"{BASE_URL}/{module}/",
        params={
            "action_type": "row",
            "action_key": action_key,
            "action": "initialize_form",
            "object_uuid": object_uuid,
        },
    )

    assert response.status_code == 200, (
        f"{module}/{action_key} failed for {session_fixture}: {response.text}"
    )

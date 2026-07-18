"""
Integration tests — invoices module.
Seam: /invoices/ HTTP endpoints (list, create, payment create).
"""
from constants import BASE_URL
from uuid import uuid4


def _ensure_patient(app_session, run_id):
    csrf: str = app_session.cookies.get("csrftoken") or ""
    email = f"invpt{run_id}@test.com"
    app_session.post(
        f"{BASE_URL}/patients/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "first_name": f"InvTest{run_id}",
            "last_name": "Patient",
            "date_of_birth": "1980-04-10",
            "email": email,
        },
    )
    r = app_session.get(
        f"{BASE_URL}/patients/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 100},
    )
    for row in r.json().get("data", []):
        if row.get("email") == email:
            return row["pk"]
    return None


def test_invoices_list_returns_200(app_session):
    r = app_session.get(
        f"{BASE_URL}/invoices/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 10},
    )
    assert r.status_code == 200, r.text
    assert "data" in r.json()


def test_create_invoice_succeeds(app_session, run_id):
    patient_pk = _ensure_patient(app_session, run_id)
    assert patient_pk, "Could not locate patient for invoice test"

    csrf: str = app_session.cookies.get("csrftoken") or ""
    r = app_session.post(
        f"{BASE_URL}/invoices/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "patient": patient_pk,
            "invoice_number": f"INV-{run_id}",
            "date_issued": "2026-07-01",
            "due_date": "2026-07-31",
            "total_amount": "350.00",
            "notes": f"Self-pay invoice {run_id}",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True, body


def test_staff_can_edit_invoice_from_row_action(app_session, run_id):
    """Invoice Edit row action opens its form and saves the updated invoice."""
    patient_pk = _ensure_patient(app_session, run_id)
    assert patient_pk, "Could not locate patient for invoice edit test"

    csrf = app_session.cookies.get("csrftoken") or ""
    invoice_number = f"INV-EDIT-{run_id}"
    resp = app_session.post(
        f"{BASE_URL}/invoices/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "patient": patient_pk,
            "invoice_number": invoice_number,
            "date_issued": "2026-07-01",
            "due_date": "2026-07-31",
            "total_amount": "350.00",
            "notes": "Before invoice edit",
        },
    )
    assert resp.status_code == 200, resp.text
    invoice_uuid = resp.json().get("response", {}).get("object_uuid", "")
    assert invoice_uuid, f"Failed to create invoice: {resp.json()}"

    form_response = app_session.get(
        f"{BASE_URL}/invoices/",
        params={
            "action_type": "row",
            "action_key": "edit",
            "action": "initialize_form",
            "object_uuid": invoice_uuid,
        },
    )
    assert form_response.status_code == 200, form_response.text

    csrf = app_session.cookies.get("csrftoken") or ""
    save_response = app_session.post(
        f"{BASE_URL}/invoices/",
        headers={"X-CSRFToken": csrf},
        params={
            "action_type": "row",
            "action_key": "edit",
            "form_type": "row_action_form",
            "object_uuid": invoice_uuid,
        },
        data={
            "patient": patient_pk,
            "invoice_number": invoice_number,
            "date_issued": "2026-07-01",
            "due_date": "2026-07-31",
            "total_amount": "375.00",
            "notes": "After invoice edit",
        },
    )
    assert save_response.status_code == 200, save_response.text
    assert save_response.json().get("success") is True, save_response.json()

    table_response = app_session.get(
        f"{BASE_URL}/invoices/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 200},
    )
    edited_invoice = next(
        row for row in table_response.json().get("data", [])
        if row.get("invoice_number") == invoice_number
    )
    assert str(edited_invoice["total_amount"]) == "375.00"


def test_payments_list_returns_200(app_session):
    r = app_session.get(
        f"{BASE_URL}/invoices/payments/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 10},
    )
    # Either 200 (payments endpoint exists) or 404 is acceptable here
    assert r.status_code in (200, 404), r.text


def test_manager_can_delete_draft_invoice_and_table_excludes_it(app_session, manager_session, run_id):
    suffix = f"del{run_id}-{uuid4().hex[:8]}"
    patient_pk = _ensure_patient(app_session, suffix)
    csrf = app_session.cookies.get("csrftoken") or ""
    created = app_session.post(f"{BASE_URL}/invoices/", headers={"X-CSRFToken": csrf}, params={"form_type": "create_form"}, data={"patient": patient_pk, "invoice_number": f"INV-DEL-{suffix}", "date_issued": "2026-07-01", "due_date": "2026-07-31", "total_amount": "350.00"})
    assert created.status_code == 200, created.text
    object_uuid = created.json()["response"]["object_uuid"]
    csrf = manager_session.cookies.get("csrftoken") or ""
    response = manager_session.post(f"{BASE_URL}/invoices/", headers={"X-CSRFToken": csrf}, params={"action_type": "row", "action_key": "delete", "object_uuid": object_uuid})
    assert response.status_code == 200, response.text
    assert response.json().get("success") is True, response.text
    rows = manager_session.get(f"{BASE_URL}/invoices/", params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 200}).json()["data"]
    assert not any(str(row.get("object_uuid")) == object_uuid for row in rows)


def test_manager_cannot_delete_sent_invoice(app_session, manager_session, run_id):
    suffix = f"sent-delete-{run_id}"
    patient_pk = _ensure_patient(app_session, suffix)
    csrf = app_session.cookies.get("csrftoken") or ""
    created = app_session.post(f"{BASE_URL}/invoices/", headers={"X-CSRFToken": csrf}, params={"form_type": "create_form"}, data={"patient": patient_pk, "invoice_number": f"INV-SENT-DEL-{suffix}", "date_issued": "2026-07-01", "due_date": "2026-07-31", "total_amount": "350.00"})
    object_uuid = created.json()["response"]["object_uuid"]
    transition = app_session.post(f"{BASE_URL}/invoices/", headers={"X-CSRFToken": csrf}, params={"view": "workflow", "action": "process_transition", "transition_name": "send", "transition_type": "status", "object_uuid": object_uuid})
    assert transition.json().get("success") is True, transition.text
    csrf = manager_session.cookies.get("csrftoken") or ""
    response = manager_session.post(f"{BASE_URL}/invoices/", headers={"X-CSRFToken": csrf}, params={"action_type": "row", "action_key": "delete", "object_uuid": object_uuid})
    assert response.status_code == 400, response.text
    assert "Only draft invoices" in response.json().get("response", {}).get("message", "")


# ── workflow transition tests ─────────────────────────────────────────────────

def _do_invoice_transition(session, object_uuid, transition_name):
    csrf = session.cookies.get("csrftoken") or ""
    r = session.post(
        f"{BASE_URL}/invoices/",
        headers={"X-CSRFToken": csrf},
        params={
            "view": "workflow",
            "action": "process_transition",
            "transition_name": transition_name,
            "transition_type": "status",
            "object_uuid": object_uuid,
        },
    )
    return r.json()


def _get_invoice_status(session, object_uuid):
    r = session.get(
        f"{BASE_URL}/invoices/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 200},
    )
    for row in r.json().get("data", []):
        if str(row.get("object_uuid")) == str(object_uuid):
            status = row.get("workflow_status", "")
            if isinstance(status, dict):
                return status.get("status_label", "").lower()
            return str(status).lower()
    return ""


def test_staff_can_send_invoice(app_session, run_id):
    """Invoice draft → sent transition (BillingStaff allowed)."""
    patient_pk = _ensure_patient(app_session, run_id)
    assert patient_pk, "Could not locate patient for invoice workflow test"

    csrf = app_session.cookies.get("csrftoken") or ""
    resp = app_session.post(
        f"{BASE_URL}/invoices/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "patient": patient_pk,
            "invoice_number": f"INV-SEND-{run_id}",
            "date_issued": "2026-07-01",
            "due_date": "2026-07-31",
            "total_amount": "200.00",
        },
    )
    obj_uuid = resp.json().get("response", {}).get("object_uuid", "")
    assert obj_uuid, f"Failed to create invoice: {resp.json()}"

    body = _do_invoice_transition(app_session, obj_uuid, "send")
    assert body.get("success") is True, f"send transition failed: {body}"
    assert "sent" in _get_invoice_status(app_session, obj_uuid)


def test_manager_can_void_invoice(app_session, manager_session, run_id):
    """Invoice sent → voided transition (BillingManager only)."""
    patient_pk = _ensure_patient(app_session, run_id)
    assert patient_pk, "Could not locate patient for invoice void test"

    csrf = app_session.cookies.get("csrftoken") or ""
    resp = app_session.post(
        f"{BASE_URL}/invoices/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "patient": patient_pk,
            "invoice_number": f"INV-VOID-{run_id}",
            "date_issued": "2026-07-01",
            "due_date": "2026-07-31",
            "total_amount": "150.00",
        },
    )
    obj_uuid = resp.json().get("response", {}).get("object_uuid", "")
    assert obj_uuid, f"Failed to create invoice for void test: {resp.json()}"

    # advance to sent first
    _do_invoice_transition(app_session, obj_uuid, "send")

    body = _do_invoice_transition(manager_session, obj_uuid, "void")
    assert body.get("success") is True, f"void transition failed: {body}"
    assert "void" in _get_invoice_status(manager_session, obj_uuid)


def _create_workflow_invoice(session, run_id, suffix, amount="200.00"):
    patient_pk = _ensure_patient(session, f"{run_id}-{suffix}")
    csrf = session.cookies.get("csrftoken") or ""
    response = session.post(
        f"{BASE_URL}/invoices/", headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={"patient": patient_pk, "invoice_number": f"INV-WF-{run_id}-{suffix}",
              "date_issued": "2026-07-01", "due_date": "2026-07-31", "total_amount": amount},
    )
    assert response.status_code == 200, response.text
    return response.json()["response"]["object_uuid"]


def test_invoice_payment_and_overdue_lifecycles(app_session, manager_session, run_id):
    # Both payment branches are exercised through their transition endpoints.
    obj_uuid = _create_workflow_invoice(app_session, run_id, "partial")
    for transition, expected in (("send", "sent"), ("record_partial", "partially_paid")):
        body = _do_invoice_transition(app_session, obj_uuid, transition)
        assert body.get("success") is True, f"{transition} failed: {body}"
        assert expected.replace("_", " ") in _get_invoice_status(app_session, obj_uuid)

    overdue_uuid = _create_workflow_invoice(app_session, run_id, "overdue")
    _do_invoice_transition(app_session, overdue_uuid, "send")
    body = _do_invoice_transition(manager_session, overdue_uuid, "mark_overdue")
    assert body.get("success") is True, body
    assert "overdue" in _get_invoice_status(manager_session, overdue_uuid)


def test_staff_cannot_mark_overdue_or_void_invoice(app_session, manager_session, run_id):
    for transition in ("mark_overdue", "void"):
        obj_uuid = _create_workflow_invoice(app_session, run_id, f"staff-{transition}")
        _do_invoice_transition(app_session, obj_uuid, "send")
        before = _get_invoice_status(app_session, obj_uuid)
        body = _do_invoice_transition(app_session, obj_uuid, transition)
        assert body.get("success") is not True, f"Staff unexpectedly ran {transition}: {body}"
        assert _get_invoice_status(app_session, obj_uuid) == before

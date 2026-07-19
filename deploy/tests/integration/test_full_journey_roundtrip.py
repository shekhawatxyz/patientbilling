"""PAT-84 live HTTP user journeys with independent tenant-Postgres checks."""
import json
import os
import time
from decimal import Decimal

import psycopg2

from constants import BASE_URL
from test_claims import _ensure_patient, _ensure_payer


def _db_row(table, object_uuid, columns="object_uuid"):
    # WorkflowState is keyed by obj_uuid (the Claim/Invoice it belongs to), not
    # object_uuid (that column is the WorkflowState row's own identity) -- confirmed
    # against the real Zango migrations (workflow_0001_initial.py,
    # workflow_0002_add_workflow_state.py).
    where_column = "obj_uuid" if table == "workflowstate" else "object_uuid"
    with psycopg2.connect(
        host=os.environ["POSTGRES_HOST"], port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    ) as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT {columns} FROM patientbilling.dynamic_models_{table} WHERE {where_column}=%s", (object_uuid,))
        return cursor.fetchone()


def _transition(session, path, object_uuid, name):
    csrf = session.cookies.get("csrftoken") or ""
    response = session.post(
        f"{BASE_URL}/{path}/", headers={"X-CSRFToken": csrf},
        params={"view": "workflow", "action": "process_transition",
                "transition_name": name, "transition_type": "status",
                "object_uuid": object_uuid},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("success") is True, f"{name} failed: {body}"
    return body


def _create_claim(session, suffix):
    payer = _ensure_payer(session, suffix)
    patient = _ensure_patient(session, suffix)
    csrf = session.cookies.get("csrftoken") or ""
    response = session.post(
        f"{BASE_URL}/claims/", headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={"patient": patient, "payer": payer,
              "claim_number": f"PAT84-{suffix}", "date_of_service": "2026-07-01",
              "diagnosis_codes": '["Z00.00"]', "total_amount": "300.00"},
    )
    assert response.status_code == 200 and response.json().get("success") is True, response.text
    claim = response.json()["response"]["object_uuid"]
    assert _db_row("claim", claim) is not None
    return claim


def _create_invoice(session, suffix, patient):
    csrf = session.cookies.get("csrftoken") or ""
    response = session.post(
        f"{BASE_URL}/invoices/", headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={"patient": patient, "invoice_number": f"PAT84-{suffix}",
              "date_issued": "2026-07-01", "due_date": "2026-07-31",
              "total_amount": "300.00"},
    )
    assert response.status_code == 200 and response.json().get("success") is True, response.text
    invoice = response.json()["response"]["object_uuid"]
    assert _db_row("invoice", invoice, "total_amount") == (Decimal("300.00"),)
    return invoice


def _logout_and_reject(session):
    csrf = session.cookies.get("csrftoken") or ""
    response = session.post(f"{BASE_URL}/api/auth/logout", headers={"X-CSRFToken": csrf})
    assert response.status_code == 204, response.text
    reused = session.get(f"{BASE_URL}/api/dashboard/", allow_redirects=False)
    assert reused.status_code in (302, 401, 403), reused.text


def test_staff_manager_invoice_and_handoff_journeys(app_session, manager_session, run_id):
    suffix = f"{run_id}-journey"

    # Staff: create patient/claim, submit, and independently verify DB state.
    patient = _ensure_patient(app_session, suffix)
    assert _db_row("patient", patient) is not None
    claim = _create_claim(app_session, suffix)
    _transition(app_session, "claims", claim, "submit")
    assert _db_row("workflowstate", claim, "current_state") == ("submitted",)
    listed = app_session.get(f"{BASE_URL}/claims/", params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 200})
    assert listed.status_code == 200 and any(str(row.get("object_uuid")) == claim for row in listed.json().get("data", []))

    # Manager adjudicates the staff-created claim. Both output fields must land
    # independently in Postgres (the two tasks are dispatched concurrently).
    _transition(manager_session, "claims", claim, "begin_review")
    _transition(manager_session, "claims", claim, "deny")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        fields = _db_row("claim", claim, "ai_denial_analysis, ai_appeal_draft")
        if fields and fields[0] is not None and fields[1]:
            break
        time.sleep(3)
    else:
        raise AssertionError(f"AI outputs did not both populate in Postgres: {fields}")
    _transition(app_session, "claims", claim, "appeal")
    _transition(manager_session, "claims", claim, "approve_appeal")
    _transition(manager_session, "claims", claim, "close")
    assert _db_row("workflowstate", claim, "current_state") == ("closed",)

    # Invoice: create, send, partial payment, paid; verify amount independently.
    invoice = _create_invoice(app_session, suffix, patient)
    _transition(app_session, "invoices", invoice, "send")
    _transition(app_session, "invoices", invoice, "record_partial")
    _transition(app_session, "invoices", invoice, "mark_paid")
    assert _db_row("invoice", invoice, "total_amount, paid_amount") == (Decimal("300.00"), Decimal("300.00"))
    assert _db_row("workflowstate", invoice, "current_state") == ("paid",)

    # Cross-role handoff uses a separate claim and manager session.
    handoff = _create_claim(app_session, f"{suffix}-handoff")
    _transition(app_session, "claims", handoff, "submit")
    _transition(manager_session, "claims", handoff, "begin_review")
    assert _db_row("workflowstate", handoff, "current_state") == ("under_review",)

    _logout_and_reject(app_session)
    _logout_and_reject(manager_session)

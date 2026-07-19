"""PAT-83: prove CRUD and workflow writes survive to the tenant Postgres schema.

These checks deliberately use psycopg2 rather than an API list/detail endpoint.
They are live-stack checks and require the Docker Postgres credentials exported by
the integration test runner.
"""
import os
import subprocess
import time
import uuid
from decimal import Decimal

import psycopg2

from constants import BASE_URL


def _db():
    return psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    )


def _row(table, object_uuid, columns="object_uuid"):
    with _db() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {columns} FROM patientbilling.dynamic_models_{table} "
            "WHERE object_uuid = %s",
            (object_uuid,),
        )
        return cursor.fetchone()


def _post(session, path, data):
    csrf = session.cookies.get("csrftoken") or ""
    response = session.post(
        f"{BASE_URL}/{path}/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data=data,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("success") is True, body
    return body["response"]["object_uuid"]


def _table_row(session, path, field, value):
    listed = session.get(
        f"{BASE_URL}/{path}/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 100},
    )
    assert listed.status_code == 200, listed.text
    for row in listed.json().get("data", []):
        if row.get(field) == value:
            return row
    raise AssertionError(f"Could not resolve {path} row for {value}")


def _restart_app():
    subprocess.run(
        ["docker", "compose", "-f", "deploy/docker_compose.yml", "restart", "app"],
        cwd="/zango",
        check=True,
        timeout=120,
    )
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "compose", "-f", "deploy/docker_compose.yml", "exec", "-T", "app", "bash", "-c", "netstat -ltn | grep -q 8000"],
            cwd="/zango",
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(2)
    raise AssertionError("app container did not become ready after restart")


def test_four_modules_round_trip_in_tenant_postgres(app_session, manager_session, run_id):
    suffix = f"{run_id}-{uuid.uuid4().hex[:8]}"
    payer_uuid = _post(app_session, "payers", {"name": f"PAT83 Payer {suffix}", "payer_id": f"PAT83-{suffix}", "contact_email": f"{suffix}@test.com"})
    patient_uuid = _post(app_session, "patients", {"first_name": f"PAT83-{suffix}", "last_name": "Patient", "date_of_birth": "1990-01-01", "email": f"pat83-{suffix}@test.com"})
    payer_pk = _table_row(app_session, "payers", "payer_id", f"PAT83-{suffix}")["pk"]
    patient_pk = _table_row(app_session, "patients", "email", f"pat83-{suffix}@test.com")["pk"]

    claim = _post(app_session, "claims", {"patient": patient_pk, "payer": payer_pk, "claim_number": f"PAT83-{suffix}", "date_of_service": "2026-07-01", "diagnosis_codes": '["Z00.00"]', "total_amount": "100.00"})
    invoice = _post(app_session, "invoices", {"patient": patient_pk, "invoice_number": f"PAT83-{suffix}", "date_issued": "2026-07-01", "due_date": "2026-07-31", "total_amount": "100.00"})
    payer, patient = payer_uuid, patient_uuid

    assert _row("insurancepayer", payer) is not None
    assert _row("patient", patient) is not None
    assert _row("claim", claim) is not None
    assert _row("invoice", invoice) is not None

    csrf = app_session.cookies.get("csrftoken") or ""
    for path, object_uuid, data in (
        ("payers", payer, {"name": f"PAT83 Edited Payer {suffix}", "payer_id": f"PAT83-{suffix}", "contact_email": f"{suffix}@test.com"}),
        ("patients", patient, {"first_name": f"PAT83 Edited {suffix}", "last_name": "Patient", "date_of_birth": "1990-01-01", "email": f"pat83-{suffix}@test.com"}),
        ("claims", claim, {"patient": patient_pk, "payer": payer_pk, "claim_number": f"PAT83-EDITED-{suffix}", "date_of_service": "2026-07-01", "diagnosis_codes": '["Z00.00"]', "total_amount": "125.00"}),
        ("invoices", invoice, {"patient": patient_pk, "invoice_number": f"PAT83-{suffix}", "date_issued": "2026-07-01", "due_date": "2026-07-31", "total_amount": "125.00"}),
    ):
        response = app_session.post(f"{BASE_URL}/{path}/", headers={"X-CSRFToken": csrf}, params={"action_type": "row", "action_key": "edit", "form_type": "row_action_form", "object_uuid": object_uuid}, data=data)
        assert response.status_code == 200 and response.json().get("success") is True, response.text

    _restart_app()
    assert _row("insurancepayer", payer, "name") == (f"PAT83 Edited Payer {suffix}",)
    assert _row("patient", patient, "first_name") == (f"PAT83 Edited {suffix}",)
    assert _row("claim", claim, "claim_number") == (f"PAT83-EDITED-{suffix}",)
    assert _row("invoice", invoice, "total_amount") == (Decimal("125.00"),)

    # Delete the draft claim before the workflow check; non-draft claims are
    # intentionally protected by the manager-only draft gate.
    csrf = manager_session.cookies.get("csrftoken") or ""
    response = manager_session.post(f"{BASE_URL}/claims/", headers={"X-CSRFToken": csrf}, params={"action_type": "row", "action_key": "delete", "object_uuid": claim})
    assert response.status_code == 200 and response.json().get("success") is True, response.text
    assert _row("claim", claim) is None

    # A separate claim transition creates a durable WorkflowState row,
    # independently checked. Its supporting rows are left for session cleanup.
    _post(app_session, "payers", {"name": f"PAT83 Workflow Payer {suffix}", "payer_id": f"PAT83-WF-{suffix}", "contact_email": f"wf-{suffix}@test.com"})
    _post(app_session, "patients", {"first_name": f"PAT83 Workflow {suffix}", "last_name": "Patient", "date_of_birth": "1990-01-01", "email": f"pat83-wf-{suffix}@test.com"})
    workflow_payer = _table_row(app_session, "payers", "payer_id", f"PAT83-WF-{suffix}")["pk"]
    workflow_patient = _table_row(app_session, "patients", "email", f"pat83-wf-{suffix}@test.com")["pk"]
    workflow_claim = _post(app_session, "claims", {"patient": workflow_patient, "payer": workflow_payer, "claim_number": f"PAT83-WF-{suffix}", "date_of_service": "2026-07-01", "diagnosis_codes": '["Z00.00"]', "total_amount": "100.00"})
    csrf = app_session.cookies.get("csrftoken") or ""
    transition = app_session.post(f"{BASE_URL}/claims/", headers={"X-CSRFToken": csrf}, params={"view": "workflow", "action": "process_transition", "transition_name": "submit", "transition_type": "status", "object_uuid": workflow_claim})
    assert transition.json().get("success") is True, transition.text
    with _db() as connection, connection.cursor() as cursor:
        # WorkflowState is registered under the "dynamic_models" app label, and its
        # obj_uuid column (not object_uuid, which is the WorkflowState row's own
        # identity) references the Claim/Invoice this state belongs to.
        cursor.execute(
            "SELECT COUNT(*) FROM patientbilling.dynamic_models_workflowstate WHERE obj_uuid = %s",
            (workflow_claim,),
        )
        assert cursor.fetchone()[0] >= 1

    # Draft-only/manager-gated deletes, then direct Postgres absence checks.
    for path, object_uuid in (("invoices", invoice), ("payers", payer), ("patients", patient)):
        csrf = manager_session.cookies.get("csrftoken") or ""
        response = manager_session.post(f"{BASE_URL}/{path}/", headers={"X-CSRFToken": csrf}, params={"action_type": "row", "action_key": "delete", "object_uuid": object_uuid})
        assert response.status_code == 200 and response.json().get("success") is True, response.text
        table = {"claims": "claim", "invoices": "invoice", "payers": "insurancepayer", "patients": "patient"}[path]
        assert _row(table, object_uuid) is None

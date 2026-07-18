"""Integration tests for the AI agent pipeline."""
import json
import os
import time
import uuid
from decimal import Decimal

import psycopg2
import pytest

from constants import APP_UUID, BASE_URL
from test_workflow_transitions import _transition


SKIP_WITHOUT_PROVIDER = pytest.mark.skipif(
    not os.environ.get("AI_PROVIDER_CONFIGURED"),
    reason="AI provider not configured — set AI_PROVIDER_CONFIGURED=1 to run",
)


def _providers(platform_session):
    r = platform_session.get(f"{BASE_URL}/api/v1/apps/{APP_UUID}/ai/providers/")
    return r.json().get("response", {}).get("providers", {}).get("records", [])


def _agent_names(platform_session):
    r = platform_session.get(f"{BASE_URL}/api/v1/apps/{APP_UUID}/ai/agents/")
    records = r.json().get("response", {}).get("agents", {}).get("records", [])
    return {a["name"] for a in records}


@pytest.fixture(autouse=True)
def require_ai_provider(platform_session):
    providers = _providers(platform_session)
    slugs = [provider.get("provider_slug", "unknown") for provider in providers]
    print(f"AI provider(s) detected: {', '.join(slugs) or 'none'}")
    if not providers:
        pytest.fail(
            "No AI provider configured. Set LOCAL_FAKE_AI=true for offline plumbing "
            "or explicitly configure a real provider before running AI tests."
        )


def test_all_three_agents_registered(platform_session):
    names = _agent_names(platform_session)
    assert "claim-validator" in names, f"Agents registered: {names}"
    assert "denial-analyzer" in names, f"Agents registered: {names}"
    assert "appeal-drafter" in names, f"Agents registered: {names}"


def _add_claim_line_item(claim_number):
    """Add the line item omitted by the claim create form."""
    with psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO patientbilling.dynamic_models_claimlineitem
                    (created_at, modified_at, object_uuid, procedure_code,
                     procedure_description, quantity, unit_price, total_price,
                     claim_id, created_by_id, modified_by_id)
                SELECT NOW(), NOW(), %s, %s, %s, %s, %s, %s, id, NULL, NULL
                FROM patientbilling.dynamic_models_claim
                WHERE claim_number = %s
                """,
                (
                    str(uuid.uuid4()),
                    "99213",
                    "Office visit",
                    1,
                    Decimal("400.00"),
                    Decimal("400.00"),
                    claim_number,
                ),
            )
            assert cursor.rowcount == 1, f"Claim {claim_number} was not found"


def _create_smoke_claim(session, run_id, suffix):
    from test_claims import _ensure_patient, _ensure_payer  # noqa: PLC0415

    payer_pk = _ensure_payer(session, f"{run_id}-{suffix}")
    patient_pk = _ensure_patient(session, f"{run_id}-{suffix}")
    claim_number = f"CLM-AI-SMOKE-{run_id}-{suffix}"
    csrf = session.cookies.get("csrftoken") or ""
    response = session.post(
        f"{BASE_URL}/claims/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "patient": patient_pk,
            "payer": payer_pk,
            "claim_number": claim_number,
            "date_of_service": "2026-07-01",
            "diagnosis_codes": '["Z00.00"]',
            "total_amount": "400.00",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json().get("success") is True, response.text
    claim_uuid = response.json()["response"]["object_uuid"]
    _add_claim_line_item(claim_number)
    return claim_uuid


def _claim_fields(session, claim_uuid):
    response = session.get(
        f"{BASE_URL}/claims/",
        params={"action": "fetch_item_details", "object_uuid": claim_uuid},
    )
    assert response.status_code == 200, response.text
    fields = response.json()["response"]["general_details"]["fields"]
    return {
        name: field.get("value") if isinstance(field, dict) else field
        for name, field in fields.items()
    }


def _decoded(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _deny_claim(session, claim_uuid):
    csrf = session.cookies.get("csrftoken") or ""
    response = session.post(
        f"{BASE_URL}/claims/",
        headers={"X-CSRFToken": csrf},
        params={
            "view": "workflow",
            "action": "process_transition",
            "transition_name": "deny",
            "transition_type": "status",
            "object_uuid": claim_uuid,
            "denial_reason_code": "CO-4",
            "denial_reason_description": "The procedure code is inconsistent with the claim diagnosis.",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@SKIP_WITHOUT_PROVIDER
def test_claim_validator_produces_output(app_session, run_id):
    claim_uuid = _create_smoke_claim(app_session, run_id, "validator")
    transition = _transition(app_session, claim_uuid, "submit")
    assert transition.get("success") is True, transition

    deadline = time.monotonic() + 60
    validation_result = None
    while time.monotonic() < deadline:
        fields = _claim_fields(app_session, claim_uuid)
        validation_result = _decoded(fields.get("ai_validation_result"))
        if validation_result is not None:
            break
        time.sleep(3)

    assert isinstance(validation_result, dict), validation_result
    assert "completeness_score" in validation_result, validation_result


@SKIP_WITHOUT_PROVIDER
def test_denial_agents_run_concurrently_and_produce_output(
    app_session, manager_session, run_id
):
    claim_uuid = _create_smoke_claim(app_session, run_id, "denial")
    submitted = _transition(app_session, claim_uuid, "submit")
    assert submitted.get("success") is True, submitted

    reviewed = _transition(manager_session, claim_uuid, "begin_review")
    assert reviewed.get("success") is True, reviewed
    denied = _deny_claim(manager_session, claim_uuid)
    assert denied.get("success") is True, denied

    deadline = time.monotonic() + 120
    denial_arrived_at = None
    appeal_arrived_at = None
    denial_analysis = None
    appeal_draft = None
    while time.monotonic() < deadline:
        fields = _claim_fields(manager_session, claim_uuid)
        denial_analysis = _decoded(fields.get("ai_denial_analysis"))
        appeal_draft = _decoded(fields.get("ai_appeal_draft"))
        if denial_analysis is not None and denial_arrived_at is None:
            denial_arrived_at = time.monotonic()
        if isinstance(appeal_draft, str) and appeal_draft.strip() and appeal_arrived_at is None:
            appeal_arrived_at = time.monotonic()
        if denial_arrived_at is not None and appeal_arrived_at is not None:
            break
        time.sleep(3)

    assert denial_arrived_at is not None, denial_analysis
    assert appeal_arrived_at is not None, appeal_draft
    assert isinstance(denial_analysis, dict), denial_analysis
    assert "root_cause" in denial_analysis, denial_analysis
    assert isinstance(appeal_draft, str) and len(appeal_draft.strip()) > 50, appeal_draft

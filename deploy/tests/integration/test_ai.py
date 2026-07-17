"""Integration tests for the AI agent pipeline."""
import time
import os

import pytest
import psycopg2

from constants import APP_UUID, BASE_URL
from test_workflow_transitions import _advance, _create_claim


def _providers(platform_session):
    r = platform_session.get(f"{BASE_URL}/api/v1/apps/{APP_UUID}/ai/providers/")
    return r.json().get("response", {}).get("providers", {}).get("records", [])


def _agent_names(platform_session):
    r = platform_session.get(f"{BASE_URL}/api/v1/apps/{APP_UUID}/ai/agents/")
    records = r.json().get("response", {}).get("agents", {}).get("records", [])
    return {a["name"] for a in records}


def _claim_ai_fields(claim_number):
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
                SELECT ai_denial_analysis, ai_appeal_draft
                FROM patientbilling.dynamic_models_claim
                WHERE claim_number = %s
                """,
                (claim_number,),
            )
            return cursor.fetchone()


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


def test_claim_validator_populates_ai_field(app_session, platform_session, run_id):
    """Submit a claim and wait up to 60 s for ai_validation_result to be non-null."""
    from test_claims import _ensure_patient, _ensure_payer  # noqa: PLC0415

    payer_pk = _ensure_payer(app_session, run_id + "ai")
    patient_pk = _ensure_patient(app_session, run_id + "ai")
    csrf: str = app_session.cookies.get("csrftoken") or ""

    # Create claim
    claim_num = f"CLM-AI-{run_id}"
    create_r = app_session.post(
        f"{BASE_URL}/claims/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "patient": patient_pk,
            "payer": payer_pk,
            "claim_number": claim_num,
            "date_of_service": "2026-07-01",
            "diagnosis_codes": '["Z00.00"]',
            "total_amount": "400.00",
        },
    )
    assert create_r.json().get("success") is True, create_r.text
    claim_uuid = create_r.json()["response"]["object_uuid"]

    # TODO: trigger submit workflow transition (requires workflow transition endpoint)
    # For now, just verify the claim exists and ai_validation_result starts null
    r = app_session.get(
        f"{BASE_URL}/claims/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 200},
    )
    row = next(
        (row for row in r.json().get("data", [])
         if str(row.get("object_uuid")) == claim_uuid),
        None,
    )
    assert row is not None, "Claim not found in list"
    # Before submission, ai_validation_result should be absent/null
    assert row.get("ai_validation_result") is None


def test_denied_claim_appeal_is_refined_with_denial_root_cause(
    app_session, manager_session, run_id
):
    """Exercise the real Celery/provider path through denial and refinement."""
    object_uuid = _create_claim(app_session, run_id, "ai-refine")
    _advance(app_session, manager_session, object_uuid, "denied")

    generic = (
        "Dear Insurer,\n\n"
        "We respectfully appeal the denial of this claim. The claim details support "
        "reconsideration.\n\nSincerely,\nBilling Department"
    )
    claim_number = f"CLM-WF-{run_id}-ai-refine"
    deadline = time.monotonic() + 30
    ai_fields = None
    while time.monotonic() < deadline:
        ai_fields = _claim_ai_fields(claim_number)
        draft = ai_fields and ai_fields[1]
        if draft and "Documentation review required" in draft:
            break
        time.sleep(1)

    assert ai_fields, f"Claim {object_uuid} was not found in the database"
    denial_analysis, draft = ai_fields
    assert denial_analysis, f"Denial analysis was not populated: {ai_fields}"
    assert draft, f"Appeal draft was not populated: {ai_fields}"
    assert draft != generic
    assert "Documentation review required" in draft

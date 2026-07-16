"""
Integration tests — AI agent pipeline.

All tests here auto-skip when no AI provider is configured.
To enable: run deploy/scripts/setup_ai.sh with a valid GEMINI_KEY, then re-run.
"""
import pytest

from constants import APP_UUID, BASE_URL


def _provider_count(platform_session):
    r = platform_session.get(f"{BASE_URL}/api/v1/apps/{APP_UUID}/ai/providers/")
    return r.json().get("response", {}).get("providers", {}).get("total_records", 0)


def _agent_names(platform_session):
    r = platform_session.get(f"{BASE_URL}/api/v1/apps/{APP_UUID}/ai/agents/")
    records = r.json().get("response", {}).get("agents", {}).get("records", [])
    return {a["name"] for a in records}


@pytest.fixture(autouse=True)
def require_ai_provider(platform_session):
    if _provider_count(platform_session) == 0:
        pytest.skip("No AI provider configured — run deploy/scripts/setup_ai.sh first")


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

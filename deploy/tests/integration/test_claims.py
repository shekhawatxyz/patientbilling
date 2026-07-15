"""
Integration tests — claims module.
Seam: /claims/, /payers/ HTTP endpoints plus workflow initial status.
"""
from constants import BASE_URL


# ── shared helpers ────────────────────────────────────────────────────────────

def _ensure_payer(app_session, run_id):
    """Create a payer (idempotent) and return its table pk."""
    csrf: str = app_session.cookies.get("csrftoken") or ""
    payer_id = f"BCBS-{run_id}"

    # Try create
    app_session.post(
        f"{BASE_URL}/payers/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "name": f"Blue Cross {run_id}",
            "payer_id": payer_id,
            "contact_email": f"claims{run_id}@bcbs.com",
        },
    )

    # Look up pk
    r = app_session.get(
        f"{BASE_URL}/payers/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 100},
    )
    for row in r.json().get("data", []):
        if row.get("payer_id") == payer_id:
            return row["pk"]
    return None


def _ensure_patient(app_session, run_id):
    """Create a patient and return its table pk."""
    csrf: str = app_session.cookies.get("csrftoken") or ""
    email = f"claimpt{run_id}@test.com"

    app_session.post(
        f"{BASE_URL}/patients/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "first_name": f"ClaimTest{run_id}",
            "last_name": "Patient",
            "date_of_birth": "1975-01-01",
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


# ── tests ─────────────────────────────────────────────────────────────────────

def test_payers_list_returns_200(app_session):
    r = app_session.get(
        f"{BASE_URL}/payers/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 10},
    )
    assert r.status_code == 200, r.text


def test_claims_list_returns_200(app_session):
    r = app_session.get(
        f"{BASE_URL}/claims/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 10},
    )
    assert r.status_code == 200, r.text


def test_create_claim_succeeds(app_session, run_id):
    payer_pk = _ensure_payer(app_session, run_id)
    patient_pk = _ensure_patient(app_session, run_id)
    assert payer_pk, "Could not locate payer"
    assert patient_pk, "Could not locate patient"

    csrf: str = app_session.cookies.get("csrftoken") or ""
    r = app_session.post(
        f"{BASE_URL}/claims/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "patient": patient_pk,
            "payer": payer_pk,
            "claim_number": f"CLM-{run_id}",
            "date_of_service": "2026-07-01",
            "diagnosis_codes": '["Z00.00"]',
            "total_amount": "500.00",
            "notes": f"Integration test claim {run_id}",
        },
    )
    # diagnosis_codes is required despite being marked optional in the form
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True, body


def test_new_claim_starts_in_draft(app_session, run_id):
    # Create a distinct claim so we can find it reliably
    payer_pk = _ensure_payer(app_session, run_id)
    patient_pk = _ensure_patient(app_session, run_id)

    csrf: str = app_session.cookies.get("csrftoken") or ""
    claim_number = f"CLM-STATUS-{run_id}"
    resp = app_session.post(
        f"{BASE_URL}/claims/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "patient": patient_pk,
            "payer": payer_pk,
            "claim_number": claim_number,
            "date_of_service": "2026-07-01",
            "diagnosis_codes": '["Z00.00"]',
            "total_amount": "250.00",
        },
    )
    claim_uuid = resp.json().get("response", {}).get("object_uuid", "")

    # Look up workflow status in table
    r = app_session.get(
        f"{BASE_URL}/claims/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 200},
    )
    status = None
    for row in r.json().get("data", []):
        if str(row.get("object_uuid")) == claim_uuid:
            status = row.get("workflow_status", "")
            break

    assert status is not None, f"Claim {claim_uuid} not found in table"
    # workflow_status is {"status_label": "Draft", "status_color": "..."} from Zango
    label = status.get("status_label", "") if isinstance(status, dict) else str(status)
    assert "draft" in label.lower(), f"Expected draft, got '{status}'"


def test_create_payer_succeeds(app_session, run_id):
    csrf: str = app_session.cookies.get("csrftoken") or ""
    r = app_session.post(
        f"{BASE_URL}/payers/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "name": f"Aetna {run_id}",
            "payer_id": f"AET-{run_id}",
            "contact_email": f"claims{run_id}@aetna.com",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True, body

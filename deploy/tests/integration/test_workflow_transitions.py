"""
Integration tests — claim workflow transitions and role-based access gates.
Seam: POST /claims/?view=workflow&action=process_transition&...
"""
from constants import BASE_URL


# ── helpers ───────────────────────────────────────────────────────────────────

def _ensure_payer(session, run_id, suffix="wf"):
    csrf = session.cookies.get("csrftoken") or ""
    payer_id = f"WF-BCBS-{run_id}-{suffix}"
    session.post(
        f"{BASE_URL}/payers/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={"name": f"WF Payer {run_id} {suffix}", "payer_id": payer_id, "contact_email": f"wf{run_id}@bcbs.com"},
    )
    r = session.get(
        f"{BASE_URL}/payers/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 200},
    )
    for row in r.json().get("data", []):
        if row.get("payer_id") == payer_id:
            return row["pk"]
    return None


def _ensure_patient(session, run_id, suffix="wf"):
    csrf = session.cookies.get("csrftoken") or ""
    email = f"wfpt{run_id}{suffix}@test.com"
    session.post(
        f"{BASE_URL}/patients/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={"first_name": f"WFTest{suffix}", "last_name": "Patient", "date_of_birth": "1980-01-01", "email": email},
    )
    r = session.get(
        f"{BASE_URL}/patients/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 200},
    )
    for row in r.json().get("data", []):
        if row.get("email") == email:
            return row["pk"]
    return None


def _create_claim(session, run_id, suffix):
    """Create a fresh claim and return its object_uuid."""
    payer_pk = _ensure_payer(session, run_id, suffix)
    patient_pk = _ensure_patient(session, run_id, suffix)
    csrf = session.cookies.get("csrftoken") or ""
    resp = session.post(
        f"{BASE_URL}/claims/",
        headers={"X-CSRFToken": csrf},
        params={"form_type": "create_form"},
        data={
            "patient": patient_pk,
            "payer": payer_pk,
            "claim_number": f"CLM-WF-{run_id}-{suffix}",
            "date_of_service": "2026-07-01",
            "diagnosis_codes": '["Z00.00"]',
            "total_amount": "300.00",
        },
    )
    return resp.json().get("response", {}).get("object_uuid", "")


def _transition(session, object_uuid, transition_name):
    """Execute a workflow transition and return the response body."""
    csrf = session.cookies.get("csrftoken") or ""
    r = session.post(
        f"{BASE_URL}/claims/",
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


def _get_status_label(session, object_uuid):
    """Return the current workflow status label for a claim."""
    r = session.get(
        f"{BASE_URL}/claims/",
        params={"view": "table", "action": "get_table_data", "page": 1, "page_size": 200},
    )
    for row in r.json().get("data", []):
        if str(row.get("object_uuid")) == str(object_uuid):
            status = row.get("workflow_status", "")
            if isinstance(status, dict):
                return status.get("status_label", "").lower()
            return str(status).lower()
    return ""


def _advance(staff_s, manager_s, object_uuid, target_state):
    """Fast-forward a claim to the target_state by executing prior transitions."""
    chain = {
        "submitted":   [("staff",   "submit")],
        "under_review": [("staff",  "submit"), ("manager", "begin_review")],
        "denied":      [("staff",   "submit"), ("manager", "begin_review"), ("manager", "deny")],
        "appealed":    [("staff",   "submit"), ("manager", "begin_review"), ("manager", "deny"), ("staff", "appeal")],
    }
    for actor, name in chain.get(target_state, []):
        s = staff_s if actor == "staff" else manager_s
        _transition(s, object_uuid, name)


# ── lifecycle tests ───────────────────────────────────────────────────────────

def test_submit_claim_transitions_to_submitted(app_session, manager_session, run_id):
    obj_uuid = _create_claim(app_session, run_id, "sub")
    body = _transition(app_session, obj_uuid, "submit")
    assert body.get("success") is True, f"submit failed: {body}"
    assert "submitted" in _get_status_label(app_session, obj_uuid)


def test_manager_begin_review(app_session, manager_session, run_id):
    obj_uuid = _create_claim(app_session, run_id, "br")
    _advance(app_session, manager_session, obj_uuid, "submitted")
    body = _transition(manager_session, obj_uuid, "begin_review")
    assert body.get("success") is True, f"begin_review failed: {body}"
    label = _get_status_label(manager_session, obj_uuid)
    assert "review" in label, f"Expected under_review, got '{label}'"


def test_manager_deny_claim(app_session, manager_session, run_id):
    obj_uuid = _create_claim(app_session, run_id, "deny")
    _advance(app_session, manager_session, obj_uuid, "under_review")
    body = _transition(manager_session, obj_uuid, "deny")
    assert body.get("success") is True, f"deny failed: {body}"
    assert "denied" in _get_status_label(manager_session, obj_uuid)


def test_staff_appeal_denied_claim(app_session, manager_session, run_id):
    obj_uuid = _create_claim(app_session, run_id, "appeal")
    _advance(app_session, manager_session, obj_uuid, "denied")
    body = _transition(app_session, obj_uuid, "appeal")
    assert body.get("success") is True, f"appeal failed: {body}"
    assert "appeal" in _get_status_label(app_session, obj_uuid)


# ── role-gate tests ───────────────────────────────────────────────────────────

def test_staff_cannot_begin_review(app_session, manager_session, run_id):
    """BillingStaff must not be able to trigger begin_review (BillingManager only)."""
    obj_uuid = _create_claim(app_session, run_id, "rbr")
    _advance(app_session, manager_session, obj_uuid, "submitted")
    body = _transition(app_session, obj_uuid, "begin_review")
    assert body.get("success") is not True, (
        f"Staff should NOT be able to begin_review but got: {body}"
    )


def test_staff_cannot_approve_claim(app_session, manager_session, run_id):
    """BillingStaff must not be able to approve a claim (BillingManager only)."""
    obj_uuid = _create_claim(app_session, run_id, "rapr")
    _advance(app_session, manager_session, obj_uuid, "under_review")
    body = _transition(app_session, obj_uuid, "approve")
    assert body.get("success") is not True, (
        f"Staff should NOT be able to approve but got: {body}"
    )


def test_manager_can_complete_approved_claim(app_session, manager_session, run_id):
    obj_uuid = _create_claim(app_session, run_id, "approve-close")
    for session, transition, expected in (
        (app_session, "submit", "submitted"),
        (manager_session, "begin_review", "under_review"),
        (manager_session, "approve", "approved"),
        (manager_session, "close", "closed"),
    ):
        body = _transition(session, obj_uuid, transition)
        assert body.get("success") is True, f"{transition} failed: {body}"
        assert expected.replace("_", " ") in _get_status_label(session, obj_uuid)


def test_manager_can_reopen_denied_claim(app_session, manager_session, run_id):
    obj_uuid = _create_claim(app_session, run_id, "reopen")
    _advance(app_session, manager_session, obj_uuid, "denied")
    body = _transition(manager_session, obj_uuid, "reopen")
    assert body.get("success") is True, body
    assert "review" in _get_status_label(manager_session, obj_uuid)


def test_manager_can_close_approved_appeal(app_session, manager_session, run_id):
    obj_uuid = _create_claim(app_session, run_id, "appeal-close")
    _advance(app_session, manager_session, obj_uuid, "appealed")
    for transition, expected in (("approve_appeal", "approved"), ("close", "closed")):
        body = _transition(manager_session, obj_uuid, transition)
        assert body.get("success") is True, f"{transition} failed: {body}"
        assert expected in _get_status_label(manager_session, obj_uuid)


def test_manager_can_close_appealed_claim_directly(app_session, manager_session, run_id):
    obj_uuid = _create_claim(app_session, run_id, "appealed-direct-close")
    _advance(app_session, manager_session, obj_uuid, "appealed")
    body = _transition(manager_session, obj_uuid, "close_from_appealed")
    assert body.get("success") is True, body
    assert "closed" in _get_status_label(manager_session, obj_uuid)


def test_staff_cannot_use_manager_only_claim_transitions(app_session, manager_session, run_id):
    cases = (("reopen", "denied"), ("approve_appeal", "appealed"), ("close", "approved"),
             ("close_from_appealed", "appealed"), ("deny", "under_review"))
    for transition, state in cases:
        obj_uuid = _create_claim(app_session, run_id, f"staff-{transition}")
        _advance(app_session, manager_session, obj_uuid, state)
        before = _get_status_label(app_session, obj_uuid)
        body = _transition(app_session, obj_uuid, transition)
        assert body.get("success") is not True, f"Staff unexpectedly ran {transition}: {body}"
        assert _get_status_label(app_session, obj_uuid) == before

"""
Unit tests for ClaimWorkflow and InvoiceWorkflow.

Seams:
  - Workflow class attributes (statuses, transitions) — structural correctness
  - done() callbacks — correct Celery task dispatch calls
"""
from unittest.mock import MagicMock, patch

from backend.claims.workflows import ClaimWorkflow
from backend.invoices.workflows import InvoiceWorkflow


# ── ClaimWorkflow structure ───────────────────────────────────────────────────

def test_claim_on_create_status_is_draft():
    assert ClaimWorkflow.Meta.on_create_status == "draft"


def test_claim_on_create_status_is_in_statuses():
    on_create = ClaimWorkflow.Meta.on_create_status
    assert on_create in ClaimWorkflow.Meta.statuses, (
        f"on_create_status '{on_create}' is missing from Meta.statuses"
    )


def test_claim_transitions_reference_valid_statuses():
    valid = set(ClaimWorkflow.Meta.statuses.keys())
    for t in ClaimWorkflow.status_transitions:
        assert t["from"] in valid, f"Transition '{t['name']}' from='{t['from']}' not in statuses"
        assert t["to"]   in valid, f"Transition '{t['name']}' to='{t['to']}' not in statuses"


def test_claim_denial_path_exists():
    transitions_by_name = {t["name"]: t for t in ClaimWorkflow.status_transitions}
    assert "submit"       in transitions_by_name
    assert "begin_review" in transitions_by_name
    assert "deny"         in transitions_by_name
    assert "appeal"       in transitions_by_name


# ── ClaimWorkflow callbacks ───────────────────────────────────────────────────

def test_submit_done_dispatches_claim_validator():
    wf = ClaimWorkflow()
    mock_obj = MagicMock()
    mock_obj.id = 42

    with patch("backend.claims.workflows.zango_task_executor") as mock_exec:
        wf.submit_done(MagicMock(), mock_obj, MagicMock())

    mock_exec.delay.assert_called_once()
    _, task_path = mock_exec.delay.call_args[0][:2]
    assert task_path == "backend.agents.tasks.run_claim_validator"


def test_deny_done_dispatches_both_agents_independently():
    wf = ClaimWorkflow()
    mock_obj = MagicMock()
    mock_obj.id = 99

    with patch("backend.claims.workflows.zango_task_executor") as mock_exec, patch(
        "backend.claims.workflows.Claim"
    ) as mock_claim:
        mock_claim.objects.filter.return_value.update.return_value = 1
        wf.deny_done(MagicMock(), mock_obj, MagicMock())

    assert mock_exec.delay.call_count == 2
    paths = [call.args[1] for call in mock_exec.delay.call_args_list]
    assert paths == [
        "backend.agents.tasks.run_denial_analyzer",
        "backend.agents.tasks.run_appeal_drafter",
    ]


def test_deny_done_passes_claim_id_as_string():
    wf = ClaimWorkflow()
    mock_obj = MagicMock()
    mock_obj.id = 7

    with patch("backend.claims.workflows.zango_task_executor") as mock_exec, patch(
        "backend.claims.workflows.Claim"
    ) as mock_claim:
        mock_claim.objects.filter.return_value.update.return_value = 1
        wf.deny_done(MagicMock(), mock_obj, MagicMock())

    kwargs = mock_exec.delay.call_args[1]
    assert "claim_id" in kwargs
    assert kwargs["claim_id"] == "7"


# ── InvoiceWorkflow structure ─────────────────────────────────────────────────

def test_invoice_on_create_status_is_draft():
    assert InvoiceWorkflow.Meta.on_create_status == "draft"


def test_invoice_transitions_reference_valid_statuses():
    valid = set(InvoiceWorkflow.Meta.statuses.keys())
    for t in InvoiceWorkflow.status_transitions:
        assert t["from"] in valid, f"Transition '{t['name']}' from='{t['from']}' not in statuses"
        assert t["to"]   in valid, f"Transition '{t['name']}' to='{t['to']}' not in statuses"

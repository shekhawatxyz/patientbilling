"""
Unit tests for backend/agents/tasks.py.

Seam: the three task functions — each must call get_agent(name).run().
"""
from unittest.mock import MagicMock, patch

import backend.agents.tasks as tasks


def test_run_claim_validator_uses_correct_agent():
    mock_agent = MagicMock()
    with patch("backend.agents.tasks.get_agent", return_value=mock_agent) as mock_get:
        tasks.run_claim_validator(claim_id=5)

    mock_get.assert_called_once_with("claim-validator")
    mock_agent.run.assert_called_once()


def test_run_denial_analyzer_does_not_chain_to_appeal_drafter():
    """The initial denial dispatch remains independent of the appeal task."""
    mock_agent = MagicMock()
    with patch("backend.agents.tasks.get_agent", return_value=mock_agent) as mock_get, patch(
        "backend.agents.tasks.zango_task_executor"
    ) as mock_exec, patch("backend.agents.tasks.connection") as mock_connection:
        mock_connection.tenant.name = "tenant-a"
        tasks.run_denial_analyzer(claim_id=5)

    mock_get.assert_called_once_with("denial-analyzer")
    assert mock_agent.run.call_count == 1
    mock_exec.delay.assert_called_once_with(
        "tenant-a",
        "backend.agents.tasks.refine_appeal_draft",
        claim_id="5",
        workflow_transaction_id=None,
    )


def test_denial_analyzer_does_not_refine_after_agent_failure():
    mock_agent = MagicMock()
    mock_agent.run.side_effect = RuntimeError("provider failed")
    with patch("backend.agents.tasks.get_agent", return_value=mock_agent), patch(
        "backend.agents.tasks.zango_task_executor"
    ) as mock_exec:
        try:
            tasks.run_denial_analyzer(claim_id=5)
        except RuntimeError:
            pass

    mock_exec.delay.assert_not_called()


def test_refine_appeal_draft_uses_appeal_agent_and_preserves_transaction():
    mock_agent = MagicMock()
    with patch("backend.agents.tasks.get_agent", return_value=mock_agent) as mock_get:
        tasks.refine_appeal_draft(claim_id=5, workflow_transaction_id="round-1")

    mock_get.assert_called_once_with("appeal-drafter")
    _, call_kwargs = mock_agent.run.call_args
    assert call_kwargs["input"] == "Refine the appeal using the denial analyzer's findings."
    assert call_kwargs["system_variables"] == {"claim_id": "5"}
    assert call_kwargs["triggered_by"] == "task"


def test_run_appeal_drafter_uses_correct_agent():
    mock_agent = MagicMock()
    with patch("backend.agents.tasks.get_agent", return_value=mock_agent) as mock_get:
        tasks.run_appeal_drafter(claim_id=5)

    mock_get.assert_called_once_with("appeal-drafter")
    mock_agent.run.assert_called_once()


def test_run_claim_validator_passes_claim_id_as_string():
    mock_agent = MagicMock()
    with patch("backend.agents.tasks.get_agent", return_value=mock_agent):
        tasks.run_claim_validator(claim_id=42)

    _, call_kwargs = mock_agent.run.call_args
    assert call_kwargs["input"]
    assert call_kwargs["system_variables"] == {"claim_id": "42"}
    assert call_kwargs["triggered_by"] == "task"

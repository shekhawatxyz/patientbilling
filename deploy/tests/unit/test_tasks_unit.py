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


def test_run_denial_analyzer_chains_to_appeal_drafter():
    """run_denial_analyzer must run the denial agent first, then chain the appeal drafter."""
    mock_agent = MagicMock()
    with patch("backend.agents.tasks.get_agent", return_value=mock_agent) as mock_get:
        tasks.run_denial_analyzer(claim_id=5)

    agent_names = [c[0][0] for c in mock_get.call_args_list]
    assert agent_names[0] == "denial-analyzer", f"First agent must be denial-analyzer, got {agent_names}"
    assert "appeal-drafter" in agent_names, f"appeal-drafter must be chained after denial-analyzer, got {agent_names}"
    assert mock_agent.run.call_count == 2, "Both agents must have .run() called"


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
    assert call_kwargs.get("variables", {}).get("claim_id") == "42"

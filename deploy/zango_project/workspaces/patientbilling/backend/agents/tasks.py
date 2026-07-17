from celery import shared_task
from django.db import connection
from zango.core import zango_task_executor
from zango.ai import get_agent

from .tools import (
    _current_claim_id,
    _current_output_field,
    _current_workflow_transaction_id,
)


def _run_agent(
    agent_name,
    claim_id,
    output_field,
    workflow_transaction_id=None,
    agent_input="Process claim.",
):
    claim_token = _current_claim_id.set(str(claim_id))
    field_token = _current_output_field.set(output_field)
    transaction_token = _current_workflow_transaction_id.set(
        None if workflow_transaction_id is None else str(workflow_transaction_id)
    )
    try:
        agent = get_agent(agent_name)
        agent.run(
            input=agent_input,
            system_variables={"claim_id": str(claim_id)},
            triggered_by="task",
        )
        from _workspaces.backend.claims.models import Claim

        claim = Claim.objects.get(id=int(claim_id))
        if getattr(claim, output_field) is None or (
            output_field == "ai_appeal_draft" and getattr(claim, output_field) == ""
        ):
            raise RuntimeError(f"{agent_name} completed without populating {output_field}")
    finally:
        _current_output_field.reset(field_token)
        _current_claim_id.reset(claim_token)
        _current_workflow_transaction_id.reset(transaction_token)


@shared_task
def run_claim_validator(claim_id, workflow_transaction_id=None):
    _run_agent("claim-validator", claim_id, "ai_validation_result", workflow_transaction_id)


@shared_task
def run_denial_analyzer(claim_id, workflow_transaction_id=None):
    _run_agent("denial-analyzer", claim_id, "ai_denial_analysis", workflow_transaction_id)
    zango_task_executor.delay(
        connection.tenant.name,
        "backend.agents.tasks.refine_appeal_draft",
        claim_id=str(claim_id),
        workflow_transaction_id=(
            None if workflow_transaction_id is None else str(workflow_transaction_id)
        ),
    )


@shared_task
def run_appeal_drafter(claim_id, workflow_transaction_id=None):
    _run_agent("appeal-drafter", claim_id, "ai_appeal_draft", workflow_transaction_id)


@shared_task
def refine_appeal_draft(claim_id, workflow_transaction_id=None):
    _run_agent(
        "appeal-drafter",
        claim_id,
        "ai_appeal_draft",
        workflow_transaction_id,
        agent_input="Refine the appeal using the denial analyzer's findings.",
    )

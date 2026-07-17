from contextvars import ContextVar
import logging

from zango.ai.tools import ToolParam, ToolSafety, tool

logger = logging.getLogger(__name__)

_current_claim_id: ContextVar[str | None] = ContextVar("_current_claim_id", default=None)
_current_output_field: ContextVar[str | None] = ContextVar("_current_output_field", default=None)
_current_workflow_transaction_id: ContextVar[str | None] = ContextVar(
    "_current_workflow_transaction_id", default=None
)
_current_ai_write_result: ContextVar[dict | None] = ContextVar(
    "_current_ai_write_result", default=None
)
_current_appeal_refinement: ContextVar[bool] = ContextVar(
    "_current_appeal_refinement", default=False
)


def _mark_untrusted_text(label: str, value: str) -> str:
    return f"<<< UNTRUSTED {label} >>>\n{value}\n<<< END UNTRUSTED {label} >>>"


def _bound_claim():
    from _workspaces.backend.claims.models import Claim

    claim_id = _current_claim_id.get()
    if claim_id is None:
        raise RuntimeError("No claim_id in context — task must set _current_claim_id before calling the agent")
    return Claim.objects.get(id=int(claim_id))


@tool(
    name="get_claim_details",
    description="Retrieve full claim details including line items, diagnosis codes, and amounts.",
    safety=ToolSafety.READ_ONLY,
)
def get_claim_details() -> dict:
    from _workspaces.backend.claims.models import Claim, ClaimLineItem

    claim_id = _current_claim_id.get()
    if claim_id is None:
        raise RuntimeError("No claim_id in context — task must set _current_claim_id before calling the agent")
    claim = Claim.objects.get(id=int(claim_id))
    line_items = ClaimLineItem.objects.filter(claim=claim)
    details = {
        "claim_number": claim.claim_number,
        "date_of_service": str(claim.date_of_service),
        "diagnosis_codes": claim.diagnosis_codes,
        "total_amount": str(claim.total_amount),
        "denial_reason_code": claim.denial_reason_code,
        "denial_reason_description": claim.denial_reason_description,
        "notes": _mark_untrusted_text("CLAIM NOTES", claim.notes),
        "line_items": [
            {
                "procedure_code": li.procedure_code,
                "procedure_description": _mark_untrusted_text(
                    "PROCEDURE DESCRIPTION", li.procedure_description
                ),
                "quantity": li.quantity,
                "unit_price": str(li.unit_price),
                "total_price": str(li.total_price),
            }
            for li in line_items
        ],
    }
    if claim.ai_denial_analysis is not None:
        details["ai_denial_analysis"] = claim.ai_denial_analysis
    return details


@tool(
    name="get_patient_insurance",
    description="Retrieve patient insurance information for a claim.",
    safety=ToolSafety.READ_ONLY,
)
def get_patient_insurance() -> dict:
    patient = _bound_claim().patient
    return {
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "insurance_provider": patient.insurance_provider,
        "insurance_policy_number": patient.insurance_policy_number,
        "insurance_group_number": patient.insurance_group_number,
    }


@tool(
    name="update_claim_ai_result",
    description="Write AI analysis results back to the claim record.",
    safety=ToolSafety.WRITE,
    memory_policy="exclude",
)
def update_claim_ai_result(
    value: str = ToolParam(description="Value to write (JSON string for JSON fields, plain text for ai_appeal_draft)"),
) -> dict:
    import json as _json
    from _workspaces.backend.claims.models import Claim

    claim_id = _current_claim_id.get()
    field = _current_output_field.get()
    if claim_id is None:
        raise RuntimeError("No claim_id in context — task must set _current_claim_id before calling the agent")
    if field not in {"ai_validation_result", "ai_denial_analysis", "ai_appeal_draft"}:
        raise RuntimeError("No valid output field in context — task must bind _current_output_field")

    if field in ("ai_validation_result", "ai_denial_analysis"):
        try:
            parsed = _json.loads(value)
        except (TypeError, ValueError, _json.JSONDecodeError) as exc:
            raise ValueError("AI result must be valid JSON") from exc
    else:
        parsed = value

    workflow_transaction_id = _current_workflow_transaction_id.get()
    if workflow_transaction_id is not None:
        from django.contrib.contenttypes.models import ContentType
        from django.db import transaction
        from _workspaces.packages.workflow.base.models import WorkflowState

        with transaction.atomic():
            claim = Claim.objects.get(id=int(claim_id))
            if (
                field == "ai_appeal_draft"
                and not _current_appeal_refinement.get()
                and claim.ai_denial_analysis is not None
            ):
                logger.info(
                    "Discarding initial appeal write for claim %s because denial analysis is available",
                    claim_id,
                )
                result = {"updated": None, "stale": True}
                _current_ai_write_result.set(result)
                return result
            claim_content_type = ContentType.objects.get_for_model(Claim)
            workflow_state = (
                WorkflowState.objects.select_for_update()
                .filter(
                    content_type=claim_content_type,
                    obj_uuid=claim.object_uuid,
                )
                .first()
            )
            current_transaction_id = (
                str(workflow_state.transaction.id)
                if workflow_state is not None and workflow_state.transaction is not None
                else None
            )
            if current_transaction_id != str(workflow_transaction_id):
                logger.warning(
                    "Discarding stale AI result for claim %s from workflow transaction %s; "
                    "current transaction is %s",
                    claim_id,
                    workflow_transaction_id,
                    current_transaction_id,
                )
                result = {"updated": None, "stale": True}
                _current_ai_write_result.set(result)
                return result

            Claim.objects.filter(id=int(claim_id)).update(**{field: parsed})
    else:
        # Direct tool callers predating the task-bound transaction context retain
        # the existing behavior; Celery-dispatched agents always bind the token.
        Claim.objects.filter(id=int(claim_id)).update(**{field: parsed})
    result = {"updated": field, "claim_id": claim_id}
    _current_ai_write_result.set(result)
    return result

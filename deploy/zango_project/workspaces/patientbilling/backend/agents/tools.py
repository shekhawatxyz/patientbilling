from contextvars import ContextVar

from zango.ai.tools import ToolParam, ToolSafety, tool

_current_claim_id: ContextVar[str | None] = ContextVar("_current_claim_id", default=None)
_current_output_field: ContextVar[str | None] = ContextVar("_current_output_field", default=None)


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
    return {
        "claim_number": claim.claim_number,
        "date_of_service": str(claim.date_of_service),
        "diagnosis_codes": claim.diagnosis_codes,
        "total_amount": str(claim.total_amount),
        "denial_reason_code": claim.denial_reason_code,
        "denial_reason_description": claim.denial_reason_description,
        "notes": claim.notes,
        "line_items": [
            {
                "procedure_code": li.procedure_code,
                "procedure_description": li.procedure_description,
                "quantity": li.quantity,
                "unit_price": str(li.unit_price),
                "total_price": str(li.total_price),
            }
            for li in line_items
        ],
    }


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
    Claim.objects.filter(id=int(claim_id)).update(**{field: parsed})
    return {"updated": field, "claim_id": claim_id}

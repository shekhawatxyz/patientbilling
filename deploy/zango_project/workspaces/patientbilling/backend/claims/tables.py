from _workspaces.packages.crud.table.base import ModelTable
from _workspaces.packages.crud.table.column import ModelCol, StringCol, ActionsCol
from .models import Claim
from .forms import ClaimForm


class ClaimTable(ModelTable):
    claim_number = ModelCol(display_as="Claim #", searchable=True, sortable=True)
    date_of_service = ModelCol(display_as="Date of Service", sortable=True)
    total_amount = ModelCol(display_as="Total Amount", sortable=True)
    ai_validation_result = ModelCol(display_as="AI Validation Result")
    ai_denial_analysis = ModelCol(display_as="AI Denial Analysis")
    ai_appeal_draft = ModelCol(display_as="AI Appeal Draft")
    actions = ActionsCol(display_as="Actions")

    row_actions = [
        {
            "name": "Edit",
            "key": "edit",
            "description": "Edit claim",
            "type": "form",
            "form": ClaimForm,
            "roles": [],
        },
    ]
    table_actions = []

    class Meta:
        model = Claim
        fields = [
            "claim_number",
            "date_of_service",
            "total_amount",
            "ai_validation_result",
            "ai_denial_analysis",
            "ai_appeal_draft",
        ]
        row_selector = {"enabled": False, "multi": False}

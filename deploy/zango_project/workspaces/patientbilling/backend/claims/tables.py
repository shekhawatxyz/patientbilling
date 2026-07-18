from _workspaces.packages.crud.table.base import ModelTable
from _workspaces.packages.crud.table.column import ModelCol, StringCol, ActionsCol
from .models import Claim
from .forms import ClaimForm


class ClaimTable(ModelTable):
    claim_number = ModelCol(display_as="Claim #", searchable=True, sortable=True)
    date_of_service = ModelCol(display_as="Date of Service", sortable=True)
    total_amount = ModelCol(display_as="Total Amount", sortable=True)
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
        {"name": "Delete", "key": "delete", "description": "Delete claim", "type": "simple", "roles": []},
    ]
    table_actions = []

    def process_row_action_delete(self, request, obj):
        obj.delete()
        return True, {"message": "Claim deleted successfully."}

    class Meta:
        model = Claim
        fields = ["claim_number", "date_of_service", "total_amount"]
        row_selector = {"enabled": False, "multi": False}

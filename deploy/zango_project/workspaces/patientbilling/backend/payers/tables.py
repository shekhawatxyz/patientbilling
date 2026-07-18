from _workspaces.packages.crud.table.base import ModelTable
from _workspaces.packages.crud.table.column import ModelCol, ActionsCol
from .models import InsurancePayer
from .forms import InsurancePayerForm


class InsurancePayerTable(ModelTable):
    name = ModelCol(display_as="Payer Name", searchable=True, sortable=True)
    payer_id = ModelCol(display_as="Payer ID", searchable=True)
    contact_email = ModelCol(display_as="Contact Email", searchable=True)
    actions = ActionsCol(display_as="Actions")

    row_actions = [
        {
            "name": "Edit",
            "key": "edit",
            "description": "Edit payer",
            "type": "form",
            "form": InsurancePayerForm,
            "roles": [],
        },
        {"name": "Delete", "key": "delete", "description": "Delete payer", "type": "simple", "roles": []},
    ]
    table_actions = []

    def process_row_action_delete(self, request, obj):
        obj.delete()
        return True, {"message": "Payer deleted successfully."}

    class Meta:
        model = InsurancePayer
        fields = ["name", "payer_id", "contact_email"]
        row_selector = {"enabled": False, "multi": False}

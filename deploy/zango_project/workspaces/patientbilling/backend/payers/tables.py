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
    ]
    table_actions = []

    class Meta:
        model = InsurancePayer
        fields = ["name", "payer_id", "contact_email"]
        row_selector = {"enabled": False, "multi": False}

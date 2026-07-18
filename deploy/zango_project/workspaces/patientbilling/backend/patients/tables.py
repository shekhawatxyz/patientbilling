from _workspaces.packages.crud.table.base import ModelTable
from _workspaces.packages.crud.table.column import ModelCol, ActionsCol
from .models import Patient
from .forms import PatientForm


class PatientTable(ModelTable):
    first_name = ModelCol(display_as="First Name", searchable=True, sortable=True)
    last_name = ModelCol(display_as="Last Name", searchable=True, sortable=True)
    date_of_birth = ModelCol(display_as="DOB", sortable=True)
    phone = ModelCol(display_as="Phone", searchable=True)
    email = ModelCol(display_as="Email", searchable=True)
    insurance_provider = ModelCol(display_as="Insurance", searchable=True)
    actions = ActionsCol(display_as="Actions")

    row_actions = [
        {
            "name": "Edit",
            "key": "edit",
            "description": "Edit patient record",
            "type": "form",
            "form": PatientForm,
            "roles": [],
        },
        {"name": "Delete", "key": "delete", "description": "Delete patient record", "type": "simple", "roles": []},
    ]
    table_actions = []

    def process_row_action_delete(self, request, obj):
        obj.delete()
        return True, {"message": "Patient deleted successfully."}

    class Meta:
        model = Patient
        fields = [
            "first_name", "last_name", "date_of_birth",
            "phone", "email", "insurance_provider",
        ]
        row_selector = {"enabled": False, "multi": False}

from _workspaces.packages.crud.table.base import ModelTable
from _workspaces.packages.crud.table.column import ModelCol, StringCol, ActionsCol
from .models import Claim
from .forms import ClaimForm
from _workspaces.packages.workflow.base.models import WorkflowState


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
        {"name": "Delete", "key": "delete", "description": "Delete claim", "type": "simple", "roles": ["BillingManager"]},
    ]
    table_actions = []

    def can_perform_row_action_delete(self, request, obj):
        return self.user_role.name == "BillingManager"

    def process_row_action_delete(self, request, obj):
        if self.user_role.name != "BillingManager":
            return False, {"message": "Only BillingManager can delete claims."}
        status = WorkflowState.objects.filter(obj_uuid=obj.object_uuid).values_list("current_state", flat=True).first()
        if status != "draft":
            return False, {"message": "Only draft claims can be deleted."}
        obj.delete()
        return True, {"message": "Claim deleted successfully."}

    class Meta:
        model = Claim
        fields = ["claim_number", "date_of_service", "total_amount"]
        row_selector = {"enabled": False, "multi": False}

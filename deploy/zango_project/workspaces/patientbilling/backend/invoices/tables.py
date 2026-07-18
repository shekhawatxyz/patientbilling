from _workspaces.packages.crud.table.base import ModelTable
from _workspaces.packages.crud.table.column import ModelCol, ActionsCol, StatusCol
from .models import Invoice
from .forms import InvoiceForm


class InvoiceTable(ModelTable):
    invoice_number = ModelCol(display_as="Invoice #", searchable=True, sortable=True)
    date_issued = ModelCol(display_as="Date Issued", sortable=True)
    due_date = ModelCol(display_as="Due Date", sortable=True)
    total_amount = ModelCol(display_as="Total ($)", sortable=True)
    paid_amount = ModelCol(display_as="Paid ($)", sortable=True)
    status = StatusCol(display_as="Status")
    actions = ActionsCol(display_as="Actions")

    row_actions = [
        {
            "name": "Edit",
            "key": "edit",
            "description": "Edit invoice",
            "type": "form",
            "form": InvoiceForm,
            "roles": [],
        },
        {"name": "Delete", "key": "delete", "description": "Delete invoice", "type": "simple", "roles": []},
    ]

    def process_row_action_delete(self, request, obj):
        obj.delete()
        return True, {"message": "Invoice deleted successfully."}

    class Meta:
        model = Invoice
        fields = ["invoice_number", "date_issued", "due_date", "total_amount", "paid_amount"]
        row_selector = {"enabled": False, "multi": False}

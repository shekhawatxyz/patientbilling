from _workspaces.packages.crud.forms import BaseForm
from _workspaces.packages.crud.form_fields import ModelField
from .models import Invoice


class InvoiceForm(BaseForm):
    patient = ModelField(label="Patient", required=True)
    invoice_number = ModelField(label="Invoice Number", required=True, placeholder="INV-2026-001")
    date_issued = ModelField(label="Date Issued", required=True)
    due_date = ModelField(label="Due Date", required=True)
    total_amount = ModelField(label="Total Amount ($)", required=True)
    notes = ModelField(label="Notes", required=False)

    class Meta:
        model = Invoice
        title = "Invoice"
        order = ["patient", "invoice_number", "date_issued", "due_date", "total_amount", "notes"]
        reload_on_success = True

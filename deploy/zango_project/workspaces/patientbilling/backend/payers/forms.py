from _workspaces.packages.crud.forms import BaseForm
from _workspaces.packages.crud.form_fields import ModelField
from .models import InsurancePayer


class InsurancePayerForm(BaseForm):
    name = ModelField(label="Payer Name", required=True, placeholder="Insurance Company Name")
    payer_id = ModelField(label="Payer ID", required=True, placeholder="e.g. BCBS001")
    contact_email = ModelField(label="Contact Email", required=False, placeholder="claims@insurer.com")

    class Meta:
        model = InsurancePayer
        title = "Insurance Payer"
        order = ["name", "payer_id", "contact_email"]
        reload_on_success = True

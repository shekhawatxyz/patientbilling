from _workspaces.packages.crud.forms import BaseForm
from _workspaces.packages.crud.form_fields import ModelField
from .models import Claim


class ClaimForm(BaseForm):
    patient = ModelField(label="Patient", required=True)
    payer = ModelField(label="Insurance Payer", required=True)
    claim_number = ModelField(label="Claim Number", required=True, placeholder="CLM-2026-001")
    date_of_service = ModelField(label="Date of Service", required=True)
    total_amount = ModelField(label="Total Amount ($)", required=True)
    diagnosis_codes = ModelField(label="Diagnosis Codes (JSON)", required=False, placeholder='["Z00.00"]')
    notes = ModelField(label="Notes", required=False)

    class Meta:
        model = Claim
        title = "Claim"
        order = [
            "patient", "payer", "claim_number", "date_of_service",
            "total_amount", "diagnosis_codes", "notes",
        ]
        reload_on_success = True

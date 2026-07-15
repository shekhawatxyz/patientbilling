from _workspaces.packages.crud.forms import BaseForm
from _workspaces.packages.crud.form_fields import ModelField
from .models import Patient


class PatientForm(BaseForm):
    first_name = ModelField(label="First Name", required=True, placeholder="First name")
    last_name = ModelField(label="Last Name", required=True, placeholder="Last name")
    date_of_birth = ModelField(label="Date of Birth", required=True)
    phone = ModelField(label="Phone", required=False, placeholder="+1 555 000 0000")
    email = ModelField(label="Email", required=False, placeholder="patient@example.com")
    address = ModelField(label="Address", required=False, placeholder="Street, City, State, ZIP")
    insurance_provider = ModelField(label="Insurance Provider", required=False)
    insurance_policy_number = ModelField(label="Policy Number", required=False)
    insurance_group_number = ModelField(label="Group Number", required=False)

    class Meta:
        model = Patient
        title = "Patient"
        order = [
            "first_name", "last_name", "date_of_birth", "phone", "email",
            "address", "insurance_provider", "insurance_policy_number",
            "insurance_group_number",
        ]
        reload_on_success = True

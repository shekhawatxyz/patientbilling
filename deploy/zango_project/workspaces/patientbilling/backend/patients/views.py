from _workspaces.packages.crud.base.views import BaseCrudView
from .tables import PatientTable
from .forms import PatientForm


class PatientCrudView(BaseCrudView):
    page_title = "Patients"
    add_btn_title = "Add Patient"
    table = PatientTable
    form = PatientForm

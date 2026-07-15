from _workspaces.packages.crud.base.views import BaseCrudView
from .tables import InsurancePayerTable
from .forms import InsurancePayerForm


class InsurancePayerCrudView(BaseCrudView):
    page_title = "Insurance Payers"
    add_btn_title = "Add Payer"
    table = InsurancePayerTable
    form = InsurancePayerForm

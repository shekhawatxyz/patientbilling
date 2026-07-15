from _workspaces.packages.crud.base.views import BaseCrudView
from .tables import InvoiceTable
from .forms import InvoiceForm
from .workflows import InvoiceWorkflow


class InvoiceCrudView(BaseCrudView):
    page_title = "Invoices"
    add_btn_title = "Add Invoice"
    table = InvoiceTable
    form = InvoiceForm
    workflow = InvoiceWorkflow

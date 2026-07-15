from _workspaces.packages.crud.base.views import BaseCrudView
from .tables import ClaimTable
from .forms import ClaimForm
from .workflows import ClaimWorkflow


class ClaimCrudView(BaseCrudView):
    page_title = "Claims"
    add_btn_title = "Add Claim"
    table = ClaimTable
    form = ClaimForm
    workflow = ClaimWorkflow

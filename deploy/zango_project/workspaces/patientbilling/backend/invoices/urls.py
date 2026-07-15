from django.urls import re_path
from .views import InvoiceCrudView

urlpatterns = [
    re_path(r"^", InvoiceCrudView.as_view(), name="invoices"),
]

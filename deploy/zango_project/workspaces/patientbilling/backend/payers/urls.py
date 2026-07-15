from django.urls import re_path
from .views import InsurancePayerCrudView

urlpatterns = [
    re_path(r"^", InsurancePayerCrudView.as_view(), name="payers"),
]

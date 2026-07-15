from django.urls import re_path
from .views import PatientCrudView

urlpatterns = [
    re_path(r"^", PatientCrudView.as_view(), name="patients"),
]

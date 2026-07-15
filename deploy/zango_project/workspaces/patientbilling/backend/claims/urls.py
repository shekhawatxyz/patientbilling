from django.urls import re_path
from .views import ClaimCrudView

urlpatterns = [
    re_path(r"^", ClaimCrudView.as_view(), name="claims"),
]

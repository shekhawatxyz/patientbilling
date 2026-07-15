from django.urls import re_path

from .views import AppView, DashboardAPIView, RedirectAppView

urlpatterns = [
    re_path(r"^api/dashboard/$", DashboardAPIView.as_view()),
    re_path(r"^app/", AppView.as_view()),
    re_path(r"^$", RedirectAppView.as_view()),
    re_path(r"^login/", RedirectAppView.as_view()),
]

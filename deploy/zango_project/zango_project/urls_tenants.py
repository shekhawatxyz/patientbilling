from django.contrib import admin
from django.contrib.auth import logout
from django.urls import include, path
from django.http import HttpResponse
from django.views import View


class FrontendLogoutView(View):
    """Handle the deployed frontend's POST logout URL without a slash."""

    def post(self, request, *args, **kwargs):
        logout(request)
        return HttpResponse(status=204)


urlpatterns = [
    # Resolve this exact URL before Zango's tenant URL include. APPEND_SLASH
    # cannot redirect it while preserving the frontend's POST request.
    path("api/auth/logout", FrontendLogoutView.as_view(), name="frontend-logout"),
    path("admin/", admin.site.urls),
    path("", include("zango.config.urls_tenants")),
]

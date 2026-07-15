from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.generic import TemplateView, View


class AppView(TemplateView):
    template_name = "app.html"


class RedirectAppView(View):
    def get(self, request, *args, **kwargs):
        return redirect("/app")


class DashboardAPIView(View):
    def get(self, request, *args, **kwargs):
        from _workspaces.backend.claims.models import Claim

        total = Claim.objects.count()
        denied = Claim.objects.filter(
            workflow_status__in=["denied"]
        ).count()
        pending = Claim.objects.filter(
            workflow_status__in=["submitted", "under_review"]
        ).count()
        denial_rate = round((denied / total * 100), 1) if total else 0.0

        pending_revenue_qs = Claim.objects.filter(
            workflow_status__in=["submitted", "under_review", "approved"]
        )
        pending_revenue = sum(
            c.total_amount for c in pending_revenue_qs if c.total_amount
        )

        recent_claims = []
        for c in Claim.objects.order_by("-created_at")[:10]:
            recent_claims.append({
                "id": c.id,
                "claim_number": c.claim_number,
                "patient": str(c.patient) if c.patient_id else "",
                "total_amount": str(c.total_amount),
                "workflow_status": c.workflow_status,
            })

        return JsonResponse({
            "success": True,
            "response": {
                "total_claims": total,
                "pending_claims": pending,
                "denial_rate": denial_rate,
                "pending_revenue": float(pending_revenue),
                "recent_claims": recent_claims,
            },
        })

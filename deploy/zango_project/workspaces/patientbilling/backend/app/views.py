from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
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
        if not request.user.is_authenticated:
            return JsonResponse({"success": False, "error": "Authentication required"}, status=403)

        from _workspaces.backend.claims.models import Claim
        from _workspaces.packages.workflow.base.models import WorkflowState

        claim_ct = ContentType.objects.get_for_model(Claim)

        denied = WorkflowState.objects.filter(
            content_type=claim_ct, current_state="denied"
        ).count()
        adjudicated = WorkflowState.objects.filter(
            content_type=claim_ct, current_state__in=["approved", "denied"]
        ).count()
        pending = WorkflowState.objects.filter(
            content_type=claim_ct, current_state__in=["submitted", "under_review"]
        ).count()
        total = Claim.objects.count()
        denial_rate = round((denied / adjudicated * 100), 1) if adjudicated else 0.0

        pending_uuids = WorkflowState.objects.filter(
            content_type=claim_ct,
            current_state__in=["submitted", "under_review", "approved"],
        ).values_list("obj_uuid", flat=True)
        pending_revenue = sum(
            c.total_amount
            for c in Claim.objects.filter(object_uuid__in=pending_uuids)
            if c.total_amount
        )

        validator_pending_uuids = WorkflowState.objects.filter(
            content_type=claim_ct,
            current_state__in=["submitted", "under_review"],
        ).values_list("obj_uuid", flat=True)
        denial_pending_uuids = WorkflowState.objects.filter(
            content_type=claim_ct,
            current_state__in=["denied", "appealed"],
        ).values_list("obj_uuid", flat=True)
        pending_ai_tasks = (
            Claim.objects.filter(
                object_uuid__in=validator_pending_uuids,
                ai_validation_result__isnull=True,
            ).count()
            + Claim.objects.filter(
                Q(ai_denial_analysis__isnull=True) | Q(ai_appeal_draft=""),
                object_uuid__in=denial_pending_uuids,
            ).count()
        )

        ws_map = {
            str(ws.obj_uuid): ws.current_state
            for ws in WorkflowState.objects.filter(content_type=claim_ct)
        }
        recent_claims = []
        for c in Claim.objects.order_by("-created_at")[:10]:
            recent_claims.append({
                "id": c.id,
                "claim_number": c.claim_number,
                "patient": str(c.patient) if c.patient_id else "",
                "total_amount": str(c.total_amount),
                "workflow_status": ws_map.get(str(c.object_uuid), "draft"),
            })

        return JsonResponse({
            "success": True,
            "response": {
                "total_claims": total,
                "pending_claims": pending,
                "denial_rate": denial_rate,
                "pending_revenue": float(pending_revenue),
                "pending_ai_tasks": pending_ai_tasks,
                "recent_claims": recent_claims,
            },
        })

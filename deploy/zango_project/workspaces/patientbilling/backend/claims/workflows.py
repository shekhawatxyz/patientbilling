from django.db import connection
from zango.core import zango_task_executor
from _workspaces.packages.workflow.base.engine import WorkflowBase
from .models import Claim


class ClaimWorkflow(WorkflowBase):
    status_transitions = [
        {
            "name": "submit",
            "display": "Submit",
            "from": "draft",
            "to": "submitted",
            "roles": ["BillingStaff", "BillingManager"],
        },
        {
            "name": "begin_review",
            "display": "Begin Review",
            "from": "submitted",
            "to": "under_review",
            "roles": ["BillingManager"],
        },
        {
            "name": "approve",
            "display": "Approve",
            "from": "under_review",
            "to": "approved",
            "roles": ["BillingManager"],
        },
        {
            "name": "deny",
            "display": "Deny",
            "from": "under_review",
            "to": "denied",
            "roles": ["BillingManager"],
        },
        {
            "name": "appeal",
            "display": "Appeal",
            "from": "denied",
            "to": "appealed",
            "roles": ["BillingStaff", "BillingManager"],
        },
        {
            "name": "reopen",
            "display": "Reopen",
            "from": "denied",
            "to": "under_review",
            "roles": ["BillingManager"],
        },
        {
            "name": "approve_appeal",
            "display": "Approve Appeal",
            "from": "appealed",
            "to": "approved",
            "roles": ["BillingManager"],
        },
        {
            "name": "close",
            "display": "Close",
            "from": "approved",
            "to": "closed",
            "roles": ["BillingManager"],
        },
        {
            "name": "close_from_appealed",
            "display": "Close",
            "from": "appealed",
            "to": "closed",
            "roles": ["BillingManager"],
        },
    ]

    class Meta:
        model = Claim
        on_create_status = "draft"
        statuses = {
            "draft": {"label": "Draft", "color": "#6c757d"},
            "submitted": {"label": "Submitted", "color": "#007bff"},
            "under_review": {"label": "Under Review", "color": "#ffc107"},
            "approved": {"label": "Approved", "color": "#28a745"},
            "denied": {"label": "Denied", "color": "#dc3545"},
            "appealed": {"label": "Appealed", "color": "#fd7e14"},
            "closed": {"label": "Closed", "color": "#343a40"},
        }

    def submit_done(self, request, object_instance, transaction_obj):
        tenant = connection.tenant.name
        zango_task_executor.delay(
            tenant,
            "backend.agents.tasks.run_claim_validator",
            claim_id=str(object_instance.id),
        )

    def submit_condition(self, request, object_instance, **kwargs):
        object_instance.full_clean()
        return True

    def deny_done(self, request, object_instance, transaction_obj):
        Claim.objects.filter(id=object_instance.id).update(
            ai_denial_analysis=None,
            ai_appeal_draft="",
        )
        tenant = connection.tenant.name
        zango_task_executor.delay(
            tenant,
            "backend.agents.tasks.run_denial_analyzer",
            claim_id=str(object_instance.id),
        )
        zango_task_executor.delay(
            tenant,
            "backend.agents.tasks.run_appeal_drafter",
            claim_id=str(object_instance.id),
        )

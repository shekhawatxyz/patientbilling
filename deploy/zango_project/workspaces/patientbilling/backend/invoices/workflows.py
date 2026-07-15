from _workspaces.packages.workflow.base.engine import WorkflowBase


class InvoiceWorkflow(WorkflowBase):
    status_transitions = [
        {"name": "send", "display": "Send", "from": "draft", "to": "sent", "roles": ["BillingStaff", "BillingManager"]},
        {"name": "mark_overdue", "display": "Mark Overdue", "from": "sent", "to": "overdue", "roles": ["BillingManager"]},
        {"name": "record_partial", "display": "Partial Payment", "from": "sent", "to": "partially_paid", "roles": ["BillingStaff", "BillingManager"]},
        {"name": "record_partial_from_overdue", "display": "Partial Payment", "from": "overdue", "to": "partially_paid", "roles": ["BillingStaff", "BillingManager"]},
        {"name": "mark_paid", "display": "Mark Paid", "from": "partially_paid", "to": "paid", "roles": ["BillingStaff", "BillingManager"]},
        {"name": "mark_paid_from_sent", "display": "Mark Paid", "from": "sent", "to": "paid", "roles": ["BillingStaff", "BillingManager"]},
        {"name": "mark_paid_from_overdue", "display": "Mark Paid", "from": "overdue", "to": "paid", "roles": ["BillingStaff", "BillingManager"]},
        {"name": "void", "display": "Void", "from": "sent", "to": "voided", "roles": ["BillingManager"]},
    ]

    class Meta:
        on_create_status = "draft"
        statuses = {
            "draft": {"label": "Draft", "color": "#6c757d"},
            "sent": {"label": "Sent", "color": "#007bff"},
            "partially_paid": {"label": "Partially Paid", "color": "#fd7e14"},
            "overdue": {"label": "Overdue", "color": "#dc3545"},
            "paid": {"label": "Paid", "color": "#28a745"},
            "voided": {"label": "Voided", "color": "#343a40"},
        }

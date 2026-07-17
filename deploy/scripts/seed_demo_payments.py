"""Create the payment rows for bootstrap_demo.sh inside the patientbilling tenant."""

from decimal import Decimal

from django.utils import timezone
from django_tenants.utils import tenant_context
from zango.apps.dynamic_models.workspace.base import Workspace
from zango.apps.shared.tenancy.models import TenantModel


tenant = TenantModel.objects.get(schema_name="patientbilling")
with tenant_context(tenant):
    with Workspace.get_plugin_source():
        from _workspaces.backend.invoices.models import Invoice, Payment

        today = timezone.now().date()
        invoice = Invoice.objects.get(invoice_number="SEED-INV-001")
        Payment.objects.get_or_create(
            invoice=invoice,
            reference_number="SEED-PAY-001",
            defaults={
                "payment_date": today,
                "amount": Decimal("200.00"),
                "payment_method": "card",
                "notes": "Demo partial payment",
            },
        )
        Invoice.objects.filter(pk=invoice.pk).update(paid_amount=Decimal("200.00"))

        invoice = Invoice.objects.get(invoice_number="SEED-INV-002")
        Payment.objects.get_or_create(
            invoice=invoice,
            reference_number="SEED-PAY-002",
            defaults={
                "payment_date": today,
                "amount": Decimal("640.00"),
                "payment_method": "bank_transfer",
                "notes": "Demo paid invoice",
            },
        )
        Invoice.objects.filter(pk=invoice.pk).update(paid_amount=Decimal("640.00"))

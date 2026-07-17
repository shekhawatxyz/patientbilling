from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_tenants.utils import schema_context

from zango.apps.shared.tenancy.models import TenantModel
from zango.core.custom_pluginbase import get_plugin_source


PATIENT_FIRST_NAME_PREFIXES = ("Test", "Listed", "ClaimTest", "InvTest", "WFTest")
CLAIM_NUMBER_PREFIXES = ("CLM-",)
INVOICE_NUMBER_PREFIXES = ("INV-",)
PAYER_ID_PREFIXES = ("BCBS-", "AET-", "WF-BCBS-")


class Command(BaseCommand):
    help = "Safely report or delete integration-test data in a workspace tenant."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument(
            "--dry-run",
            action="store_true",
            help="Print matching rows without deleting anything.",
        )
        mode.add_argument(
            "--execute",
            action="store_true",
            help="Delete the matching rows.",
        )
        parser.add_argument(
            "--created-since",
            help="Limit matches to rows created at or after this ISO-8601 timestamp.",
        )
        parser.add_argument(
            "--workspace",
            default="patientbilling",
            help="Workspace tenant to clean (default: patientbilling).",
        )

    def handle(self, *args, **options):
        created_since = self._parse_created_since(options.get("created_since"))
        tenant = self._get_tenant(options["workspace"])

        with schema_context(tenant.schema_name), get_plugin_source(tenant.name):
            from _workspaces.backend.claims.models import Claim, ClaimLineItem
            from _workspaces.backend.invoices.models import Invoice, InvoiceLineItem, Payment
            from _workspaces.backend.patients.models import Patient
            from _workspaces.backend.payers.models import InsurancePayer

            matches = self._matching_rows(
                Patient,
                Claim,
                Invoice,
                InsurancePayer,
                created_since,
            )
            self._report(matches)
            if options["execute"]:
                with transaction.atomic():
                    deleted_counts = self._delete_rows(
                        matches,
                        ClaimLineItem,
                        InvoiceLineItem,
                        Payment,
                    )
                self._report_counts(deleted_counts, heading="Deleted rows")
                self.stdout.write(self.style.SUCCESS("Deleted matching test data."))
                self._report(matches, heading="Remaining matching rows")
            else:
                self.stdout.write(self.style.WARNING("Dry run: no rows deleted."))

    @staticmethod
    def _parse_created_since(value):
        if not value:
            return None
        parsed = parse_datetime(value)
        if parsed is None:
            raise CommandError("--created-since must be a valid ISO-8601 timestamp")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    @staticmethod
    def _get_tenant(workspace):
        try:
            return TenantModel.objects.get(name=workspace)
        except TenantModel.DoesNotExist as exc:
            raise CommandError(f"Unknown workspace: {workspace}") from exc

    @staticmethod
    def _prefix_query(model, field, prefixes):
        query = Q()
        for prefix in prefixes:
            query |= Q(**{f"{field}__startswith": prefix})
        return query

    def _matching_rows(self, Patient, Claim, Invoice, InsurancePayer, created_since):
        patient_filter = self._prefix_query(
            Patient, "first_name", PATIENT_FIRST_NAME_PREFIXES
        )
        claim_filter = self._prefix_query(
            Claim, "claim_number", CLAIM_NUMBER_PREFIXES
        )
        invoice_filter = self._prefix_query(
            Invoice, "invoice_number", INVOICE_NUMBER_PREFIXES
        )
        payer_filter = self._prefix_query(
            InsurancePayer, "payer_id", PAYER_ID_PREFIXES
        )
        if created_since is not None:
            patient_filter &= Q(created_at__gte=created_since)
            claim_filter &= Q(created_at__gte=created_since)
            invoice_filter &= Q(created_at__gte=created_since)
            payer_filter &= Q(created_at__gte=created_since)

        return {
            "patients": Patient.objects.filter(patient_filter),
            "claims": Claim.objects.filter(claim_filter),
            "invoices": Invoice.objects.filter(invoice_filter),
            "payers": InsurancePayer.objects.filter(payer_filter),
        }

    @staticmethod
    def _delete_rows(matches, ClaimLineItem, InvoiceLineItem, Payment):
        claims = matches["claims"]
        invoices = matches["invoices"]
        deleted = {name: queryset.count() for name, queryset in matches.items()}
        Payment.objects.filter(invoice__in=invoices).delete()
        InvoiceLineItem.objects.filter(invoice__in=invoices).delete()
        ClaimLineItem.objects.filter(claim__in=claims).delete()
        invoices.delete()
        claims.delete()
        matches["patients"].delete()
        matches["payers"].delete()
        return deleted

    def _report(self, matches, heading="Matching rows"):
        self.stdout.write(heading + ":")
        self._report_counts(
            {name: queryset.count() for name, queryset in matches.items()}
        )

    def _report_counts(self, counts, heading="Matching rows"):
        if heading != "Matching rows":
            self.stdout.write(heading + ":")
        for name, count in counts.items():
            self.stdout.write(f"  {name}: {count}")

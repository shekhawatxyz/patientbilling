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
PAYER_NAME_PREFIXES = ("Blue Cross ", "Aetna ", "WF Payer ")
PAYER_ID_PREFIXES = ("BCBS-", "AET-", "WF-BCBS-")


class Command(BaseCommand):
    help = "Safely report or delete integration-test data in a workspace tenant."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--execute", action="store_true")
        parser.add_argument("--created-since", "--since", dest="created_since")
        parser.add_argument("--workspace", default="patientbilling")

    def handle(self, *args, **options):
        created_since = self._parse_created_since(options.get("created_since"))
        tenant = self._get_tenant(options["workspace"])

        with schema_context(tenant.schema_name), get_plugin_source(tenant.name):
            from _workspaces.backend.claims.models import Claim, ClaimLineItem
            from _workspaces.backend.invoices.models import Invoice, InvoiceLineItem, Payment
            from _workspaces.backend.patients.models import Patient
            from _workspaces.backend.payers.models import InsurancePayer

            matches = self._matching_rows(
                Patient, Claim, Invoice, InsurancePayer, created_since
            )
            self._report(matches, heading="Matching rows")
            if options["dry_run"]:
                self.stdout.write(self.style.WARNING("Dry run: no rows deleted."))
                return

            with transaction.atomic():
                deleted = self._delete_rows(
                    matches, ClaimLineItem, InvoiceLineItem, Payment
                )
            self._report_counts(deleted, heading="Deleted rows")
            self._report(matches, heading="Remaining matching rows")
            self.stdout.write(self.style.SUCCESS("Deleted matching test data."))

    @staticmethod
    def _parse_created_since(value):
        if not value:
            return None
        parsed = parse_datetime(value)
        if parsed is None:
            raise CommandError("--created-since must be a valid ISO-8601 timestamp")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed)
        return parsed

    @staticmethod
    def _get_tenant(workspace):
        try:
            return TenantModel.objects.get(name=workspace)
        except TenantModel.DoesNotExist as exc:
            raise CommandError(f"Unknown workspace: {workspace}") from exc

    @staticmethod
    def _prefix_query(field, prefixes):
        query = Q()
        for prefix in prefixes:
            query |= Q(**{f"{field}__startswith": prefix})
        return query

    def _matching_rows(self, Patient, Claim, Invoice, InsurancePayer, created_since):
        filters = {
            "patients": self._prefix_query("first_name", PATIENT_FIRST_NAME_PREFIXES),
            "claims": self._prefix_query("claim_number", CLAIM_NUMBER_PREFIXES),
            "invoices": self._prefix_query("invoice_number", INVOICE_NUMBER_PREFIXES),
            "payers": self._prefix_query("name", PAYER_NAME_PREFIXES)
            | self._prefix_query("payer_id", PAYER_ID_PREFIXES),
        }
        models = {
            "patients": Patient,
            "claims": Claim,
            "invoices": Invoice,
            "payers": InsurancePayer,
        }
        return {
            name: model.objects.filter(query & Q(created_at__gte=created_since))
            if created_since is not None
            else model.objects.filter(query)
            for name, query in filters.items()
            for model in [models[name]]
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

        # Never remove a candidate still referenced by a non-test record.
        matches["patients"].filter(claims__isnull=True, invoices__isnull=True).delete()
        matches["payers"].filter(claims__isnull=True).delete()
        return deleted

    def _report(self, matches, heading):
        self.stdout.write(f"{heading}:")
        self._report_counts(
            {name: queryset.count() for name, queryset in matches.items()}
        )

    def _report_counts(self, counts, heading=None):
        if heading:
            self.stdout.write(f"{heading}:")
        for name, count in counts.items():
            self.stdout.write(f"  {name}: {count}")

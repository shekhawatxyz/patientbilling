from django.db import models
from django.core.exceptions import ValidationError
from zango.apps.dynamic_models.models import DynamicModelBase
from zango.apps.dynamic_models.fields import ZForeignKey
from _workspaces.backend.patients.models import Patient as PatientModel
from _workspaces.backend.payers.models import InsurancePayer as InsurancePayerModel


class Claim(DynamicModelBase):
    patient = ZForeignKey(
        PatientModel,
        on_delete=models.PROTECT,
        related_name="claims",
    )
    payer = ZForeignKey(
        InsurancePayerModel,
        on_delete=models.PROTECT,
        related_name="claims",
    )
    claim_number = models.CharField(max_length=100, unique=True)
    date_of_service = models.DateField()
    diagnosis_codes = models.JSONField(default=list)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    submitted_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    approved_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    denial_reason_code = models.CharField(max_length=20, blank=True)
    denial_reason_description = models.TextField(blank=True)
    ai_validation_result = models.JSONField(null=True, blank=True)
    ai_denial_analysis = models.JSONField(null=True, blank=True)
    ai_appeal_draft = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    def clean(self):
        super().clean()
        if self.pk:
            from decimal import Decimal
            lines = list(self.line_items.all())
            line_total = sum((line.total_price for line in lines), Decimal("0"))
            if lines and self.total_amount != line_total:
                raise ValidationError({"total_amount": "Claim total must match its line items."})

    def __str__(self):
        return self.claim_number


class ClaimLineItem(DynamicModelBase):
    claim = ZForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name="line_items",
    )
    procedure_code = models.CharField(max_length=20)
    procedure_description = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def clean(self):
        super().clean()
        expected = self.quantity * self.unit_price
        if self.total_price != expected:
            raise ValidationError({"total_price": "Line total must equal quantity × unit price."})

    def __str__(self):
        return f"{self.procedure_code} x{self.quantity}"

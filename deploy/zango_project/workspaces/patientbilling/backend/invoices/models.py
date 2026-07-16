from django.db import models
from django.core.exceptions import ValidationError
from zango.apps.dynamic_models.models import DynamicModelBase
from zango.apps.dynamic_models.fields import ZForeignKey
from _workspaces.backend.patients.models import Patient as PatientModel


class Invoice(DynamicModelBase):
    patient = ZForeignKey(PatientModel, on_delete=models.PROTECT, related_name="invoices")
    invoice_number = models.CharField(max_length=100, unique=True)
    date_issued = models.DateField()
    due_date = models.DateField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    def clean(self):
        super().clean()
        if self.paid_amount < 0:
            raise ValidationError({"paid_amount": "Paid amount cannot be negative."})
        if self.paid_amount > self.total_amount:
            raise ValidationError({"paid_amount": "Paid amount cannot exceed total amount."})

    def __str__(self):
        return self.invoice_number


class InvoiceLineItem(DynamicModelBase):
    invoice = ZForeignKey(Invoice, on_delete=models.CASCADE, related_name="line_items")
    description = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.description


class Payment(DynamicModelBase):
    PAYMENT_METHOD_CHOICES = [
        ("cash", "Cash"),
        ("card", "Card"),
        ("bank_transfer", "Bank Transfer"),
    ]
    invoice = ZForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    def clean(self):
        super().clean()
        if self.amount <= 0:
            raise ValidationError({"amount": "Payment amount must be positive."})

    def __str__(self):
        return f"Payment {self.amount} for {self.invoice_id}"

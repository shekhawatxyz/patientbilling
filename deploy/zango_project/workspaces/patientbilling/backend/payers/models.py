from django.db import models
from zango.apps.dynamic_models.models import DynamicModelBase


class InsurancePayer(DynamicModelBase):
    name = models.CharField(max_length=200)
    payer_id = models.CharField(max_length=100, unique=True)
    contact_email = models.EmailField(blank=True)

    def __str__(self):
        return self.name

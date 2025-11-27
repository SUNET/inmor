from typing import TYPE_CHECKING, Any

from django.db import models
from django.db.models.functions import Now

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager


# Create your models here.
class TrustMarkType(models.Model):
    id: int
    tmtype = models.CharField(unique=True)
    autorenew = models.BooleanField(default=False)
    valid_for = models.IntegerField(default=8760)  # Means 365 days
    renewal_time = models.IntegerField(default=48)  # Means 2 days
    active = models.BooleanField(default=True)  # Means active by default

    def __str__(self):
        return self.tmtype

    class Meta:
        indexes = [
            models.Index(fields=["tmtype"]),
        ]


class TrustMark(models.Model):
    id: int
    tmt = models.ForeignKey(TrustMarkType, on_delete=models.CASCADE)
    added = models.DateTimeField(db_default=Now())
    domain = models.CharField()
    active = models.BooleanField()
    autorenew = models.BooleanField()
    valid_for = models.IntegerField()
    renewal_time = models.IntegerField()
    mark = models.CharField(null=True)
    expire_at = models.DateTimeField(null=True)

    if TYPE_CHECKING:
        additional_claims: dict[str, Any] | None
    else:
        additional_claims = models.JSONField(default=None, null=True)

    def __str__(self):
        return self.domain

    class Meta:
        unique_together = ("tmt", "domain")
        indexes = [
            models.Index(fields=["domain"]),
            models.Index(fields=["active"]),
            models.Index(fields=["tmt"]),
            models.Index(fields=["expire_at"]),
        ]

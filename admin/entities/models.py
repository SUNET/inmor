from django.db import models
from django.db.models.functions import Now
from typing import TYPE_CHECKING, Any


# Create your models here.
class Subordinate(models.Model):
    id: int
    added = models.DateTimeField(db_default=Now())
    entityid = models.CharField(unique=True)
    valid_for = models.IntegerField(default=8760)  # Means 365 days
    autorenew = models.BooleanField(default=False)
    metadata = models.CharField()
    forced_metadata = models.CharField()  # We don't query this, only store and use
    jwks = models.CharField(null=True)
    required_trustmarks = models.CharField(null=True)
    active = models.BooleanField(default=True)
    statement = models.CharField(null=True)
    if TYPE_CHECKING:
        additional_claims: dict[str, Any] | None
    else:
        additional_claims = models.JSONField(default=None, null=True)

    def __str__(self):
        return self.entityid

    class Meta:
        indexes = [
            models.Index(fields=["entityid"]),
            models.Index(fields=["valid_for"]),
            models.Index(fields=["autorenew"]),
        ]

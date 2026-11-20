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
    metadata = models.JSONField(default=dict)
    forced_metadata = models.JSONField(default=dict)
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
        permissions = [("manage_federation", "Can manage the federation")]
        indexes = [
            models.Index(fields=["entityid"]),
            models.Index(fields=["valid_for"]),
            models.Index(fields=["autorenew"]),
        ]


class PendingPublication(models.Model):
    """A committed Redis update awaiting delivery for one federation record."""

    subordinate = models.OneToOneField(Subordinate, null=True, on_delete=models.CASCADE)
    trust_mark = models.OneToOneField("trustmarks.TrustMark", null=True, on_delete=models.CASCADE)
    # The verified wire JWT cannot be reconstructed from the subordinate's stored claims.
    entity_configuration = models.TextField(default="")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(subordinate__isnull=False, trust_mark__isnull=True)
                    | models.Q(subordinate__isnull=True, trust_mark__isnull=False)
                ),
                name="publication_has_one_resource",
            )
        ]

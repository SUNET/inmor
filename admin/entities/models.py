from django.db import models
from django.db.models.functions import Now


# Create your models here.
class Subordinate(models.Model):
    id: int
    added = models.DateTimeField(db_default=Now())
    entityid = models.CharField(unique=True)
    valid_for = models.IntegerField(default=8760)  # Means 365 days
    autorenew = models.BooleanField(default=False)
    metadata_db = models.CharField()
    required_trustmarks = models.CharField(null=True)

    def __str__(self):
        return self.entityid

    class Meta:
        indexes = [
            models.Index(fields=["entityid"]),
            models.Index(fields=["valid_for"]),
            models.Index(fields=["autorenew"]),
        ]

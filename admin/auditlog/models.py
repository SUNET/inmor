"""Audit log model for tracking API operations."""

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class AuditLogEntry(models.Model):
    """Records every state-changing API operation."""

    class Action(models.TextChoices):
        CREATE = "CREATE"
        UPDATE = "UPDATE"
        DELETE = "DELETE"

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_log_entries",
    )
    auth_method = models.CharField(max_length=50)
    tenant = models.CharField(max_length=255, default="default")
    ip_address = models.GenericIPAddressField(null=True)
    action = models.CharField(max_length=10, choices=Action.choices)
    resource_type = models.CharField(max_length=100)
    resource_id = models.IntegerField(null=True)
    resource_repr = models.CharField(max_length=500)
    endpoint = models.CharField(max_length=500)
    http_method = models.CharField(max_length=10)
    snapshot_before = models.JSONField(null=True, default=None)
    snapshot_after = models.JSONField(null=True, default=None)
    diff = models.JSONField(null=True, default=None)
    response_code = models.IntegerField()
    success = models.BooleanField()
    event_type = models.CharField(max_length=100, null=True, default=None)

    class Meta:
        verbose_name = "Audit Log Entry"
        verbose_name_plural = "Audit Log Entries"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["resource_type", "resource_id"]),
            models.Index(fields=["user", "timestamp"]),
            models.Index(fields=["action", "resource_type"]),
            models.Index(fields=["resource_type", "event_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.timestamp} {self.action} {self.resource_type} {self.resource_repr}"

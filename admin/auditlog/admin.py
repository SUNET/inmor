"""Django admin configuration for audit log (read-only)."""

from django.contrib import admin
from django.http import HttpRequest

from .models import AuditLogEntry


class AuditLogEntryAdmin(admin.ModelAdmin):
    """Read-only admin view for audit log entries."""

    list_display = [
        "timestamp",
        "user",
        "auth_method",
        "tenant",
        "action",
        "resource_type",
        "resource_repr",
        "response_code",
        "event_type",
    ]
    list_filter = [
        "action",
        "resource_type",
        "auth_method",
        "tenant",
        "success",
        "event_type",
    ]
    search_fields = [
        "resource_repr",
        "user__username",
        "endpoint",
    ]
    readonly_fields = [
        "timestamp",
        "user",
        "auth_method",
        "tenant",
        "ip_address",
        "action",
        "resource_type",
        "resource_id",
        "resource_repr",
        "endpoint",
        "http_method",
        "snapshot_before",
        "snapshot_after",
        "diff",
        "response_code",
        "success",
        "event_type",
    ]
    ordering = ["-timestamp"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


admin.site.register(AuditLogEntry, AuditLogEntryAdmin)

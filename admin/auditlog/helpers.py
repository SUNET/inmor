"""Audit log helper functions called from API endpoints."""

from __future__ import annotations

from typing import Any

from django.db import models
from django.http import HttpRequest

from .diff import compute_diff, model_to_dict
from .models import AuditLogEntry


def _get_client_ip(request: HttpRequest) -> str | None:
    """Extract client IP from request, respecting X-Forwarded-For."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _get_auth_info(request: HttpRequest) -> dict[str, Any]:
    """Extract auth metadata from request.auth_result (set by CombinedAuthentication)."""
    auth_result = getattr(request, "auth_result", None)
    if auth_result is not None:
        return {
            "user": auth_result.user,
            "auth_method": auth_result.auth_method,
            "tenant": auth_result.tenant,
        }
    # Fallback for requests without auth_result (shouldn't happen in normal flow)
    if hasattr(request, "user") and request.user.is_authenticated:
        return {
            "user": request.user,
            "auth_method": "session",
            "tenant": "default",
        }
    return {
        "user": None,
        "auth_method": "unknown",
        "tenant": "default",
    }


def _resource_repr(resource_type: str, instance: models.Model | None) -> str:
    """Build a human-readable repr for the resource."""
    if instance is None:
        return ""
    return str(instance)


# ---------------------------------------------------------------------------
# Event type derivation
# ---------------------------------------------------------------------------

# Priority order for subordinate event types (highest first)
_SUBORDINATE_EVENT_PRIORITY = [
    "revocation",
    "metadata_policy_update",
    "metadata_update",
    "jwks_update",
]


def _derive_subordinate_event_type(diff: dict[str, Any]) -> str | None:
    """Derive the spec event type for a subordinate update from the diff."""
    if not diff:
        return None
    events: list[str] = []
    if "active" in diff:
        new_active = diff["active"].get("new")
        if new_active is False:
            events.append("revocation")
    if "forced_metadata" in diff:
        events.append("metadata_policy_update")
    if "metadata" in diff:
        events.append("metadata_update")
    if "jwks" in diff:
        events.append("jwks_update")
    if not events:
        return None
    # Return highest priority event
    for event in _SUBORDINATE_EVENT_PRIORITY:
        if event in events:
            return event
    return events[0]


def _derive_trustmarktype_event_type(action: str, diff: dict[str, Any] | None) -> str:
    """Derive event type for TrustMarkType operations."""
    if action == "CREATE":
        return "trustmarktype_created"
    if diff and "active" in diff:
        new_active = diff["active"].get("new")
        if new_active is False:
            return "trustmarktype_deactivated"
    return "trustmarktype_updated"


def _derive_trustmark_event_type(
    action: str, diff: dict[str, Any] | None, *, is_renew: bool = False
) -> str:
    """Derive event type for TrustMark operations."""
    if action == "CREATE":
        return "trustmark_issued"
    if is_renew:
        return "trustmark_renewed"
    if diff and "active" in diff:
        new_active = diff["active"].get("new")
        if new_active is False:
            return "trustmark_revoked"
    return "trustmark_updated"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def log_create(
    request: HttpRequest,
    resource_type: str,
    instance: models.Model,
    *,
    response_code: int = 201,
    event_type: str | None = None,
) -> AuditLogEntry:
    """Log a CREATE operation."""
    auth = _get_auth_info(request)
    snapshot_after = model_to_dict(instance)

    # Derive event_type if not explicitly provided
    if event_type is None:
        if resource_type == "TrustMarkType":
            event_type = _derive_trustmarktype_event_type("CREATE", None)
        elif resource_type == "TrustMark":
            event_type = _derive_trustmark_event_type("CREATE", None)

    return AuditLogEntry.objects.create(
        user=auth["user"],
        auth_method=auth["auth_method"],
        tenant=auth["tenant"],
        ip_address=_get_client_ip(request),
        action=AuditLogEntry.Action.CREATE,
        resource_type=resource_type,
        resource_id=instance.pk,
        resource_repr=_resource_repr(resource_type, instance),
        endpoint=request.path,
        http_method=request.method,
        snapshot_after=snapshot_after,
        response_code=response_code,
        success=200 <= response_code < 300,
        event_type=event_type,
    )


def log_update(
    request: HttpRequest,
    resource_type: str,
    instance: models.Model,
    *,
    snapshot_before: dict[str, Any],
    response_code: int = 200,
    event_type: str | None = None,
    is_renew: bool = False,
) -> AuditLogEntry:
    """Log an UPDATE operation.

    Args:
        request: The HTTP request.
        resource_type: Model name (e.g. "Subordinate").
        instance: The model instance *after* the update.
        snapshot_before: Result of ``model_to_dict()`` taken before the update.
        response_code: HTTP response code.
        event_type: Explicit event type (derived from diff if None).
        is_renew: Whether this is a renew operation (for TrustMark).
    """
    auth = _get_auth_info(request)
    snapshot_after = model_to_dict(instance)
    diff = compute_diff(snapshot_before, snapshot_after)

    # Derive event_type if not explicitly provided
    if event_type is None:
        if resource_type == "Subordinate":
            event_type = _derive_subordinate_event_type(diff)
        elif resource_type == "TrustMarkType":
            event_type = _derive_trustmarktype_event_type("UPDATE", diff)
        elif resource_type == "TrustMark":
            event_type = _derive_trustmark_event_type("UPDATE", diff, is_renew=is_renew)

    return AuditLogEntry.objects.create(
        user=auth["user"],
        auth_method=auth["auth_method"],
        tenant=auth["tenant"],
        ip_address=_get_client_ip(request),
        action=AuditLogEntry.Action.UPDATE,
        resource_type=resource_type,
        resource_id=instance.pk,
        resource_repr=_resource_repr(resource_type, instance),
        endpoint=request.path,
        http_method=request.method,
        snapshot_before=snapshot_before,
        snapshot_after=snapshot_after,
        diff=diff,
        response_code=response_code,
        success=200 <= response_code < 300,
        event_type=event_type,
    )

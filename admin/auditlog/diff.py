"""JSON diff utilities for audit log snapshots."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.db import models


def model_to_dict(instance: models.Model) -> dict[str, Any]:
    """Serialize a Django model instance to a dict of all field values.

    Handles DateTimeField, JSONField, ForeignKey (stores PK), and other
    common field types.  New columns on a model are captured automatically.
    """
    result: dict[str, Any] = {}
    for field in instance._meta.get_fields():
        if not isinstance(field, (models.Field, models.ForeignKey)):
            continue
        name = field.name
        if isinstance(field, models.ForeignKey):
            # Store the FK id, not the related object
            name = f"{field.name}_id"
            value = getattr(instance, name, None)
        else:
            value = getattr(instance, name, None)
        # Make values JSON-serializable
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        result[name] = value
    return result


def _diff_dicts(old: dict, new: dict) -> dict[str, Any]:
    """Compute a nested diff for two dicts (metadata, additional_claims, etc.).

    Returns a dict with ``added``, ``removed``, and ``changed`` keys.
    """
    all_keys = set(old) | set(new)
    added = {k: new[k] for k in all_keys if k not in old}
    removed = {k: old[k] for k in all_keys if k not in new}
    changed = {}
    for k in all_keys:
        if k in old and k in new and old[k] != new[k]:
            changed[k] = {"old": old[k], "new": new[k]}
    result: dict[str, Any] = {}
    if added:
        result["added"] = added
    if removed:
        result["removed"] = removed
    if changed:
        result["changed"] = changed
    return result


def compute_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compute a field-level diff between two model snapshots.

    For dict-valued fields, produces a nested diff with added/removed/changed.
    For scalar fields, produces ``{"old": ..., "new": ...}``.

    Returns an empty dict if nothing changed.
    """
    diff: dict[str, Any] = {}
    all_keys = set(before) | set(after)
    for key in sorted(all_keys):
        old_val = before.get(key)
        new_val = after.get(key)
        if old_val == new_val:
            continue
        # Nested diff for dict-valued fields
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            nested = _diff_dicts(old_val, new_val)
            if nested:
                diff[key] = nested
        else:
            diff[key] = {"old": old_val, "new": new_val}
    return diff

"""Tests for audit logging."""

import json

import pytest
from django.test import Client

from auditlog.diff import compute_diff, model_to_dict
from auditlog.helpers import (
    _derive_subordinate_event_type,
    _derive_trustmark_event_type,
    _derive_trustmarktype_event_type,
)
from auditlog.models import AuditLogEntry


# ---------------------------------------------------------------------------
# diff.py unit tests
# ---------------------------------------------------------------------------


class TestModelToDict:
    """Tests for model_to_dict serialization."""

    @pytest.mark.django_db
    def test_trustmarktype_serialization(self, db_with_fixtures):
        from trustmarks.models import TrustMarkType

        tmt = TrustMarkType.objects.create(
            tmtype="https://example.com/test-tmt",
            autorenew=True,
            valid_for=8760,
            renewal_time=48,
            active=True,
        )
        d = model_to_dict(tmt)
        assert d["tmtype"] == "https://example.com/test-tmt"
        assert d["autorenew"] is True
        assert d["valid_for"] == 8760
        assert d["active"] is True
        assert "id" in d

    @pytest.mark.django_db
    def test_subordinate_serialization(self, db_with_fixtures):
        from entities.models import Subordinate

        sub = Subordinate.objects.create(
            entityid="https://example.com/sub",
            metadata={"openid_relying_party": {"scope": "openid"}},
            forced_metadata={},
        )
        d = model_to_dict(sub)
        assert d["entityid"] == "https://example.com/sub"
        assert d["metadata"] == {"openid_relying_party": {"scope": "openid"}}

    @pytest.mark.django_db
    def test_fk_serialized_as_id(self, db_with_fixtures):
        from trustmarks.models import TrustMark, TrustMarkType

        tmt = TrustMarkType.objects.create(
            tmtype="https://example.com/fk-test",
            autorenew=True,
            valid_for=8760,
            renewal_time=48,
            active=True,
        )
        tm = TrustMark.objects.create(
            tmt=tmt,
            domain="https://example.com",
            active=True,
            autorenew=True,
            valid_for=8760,
            renewal_time=48,
        )
        d = model_to_dict(tm)
        assert d["tmt_id"] == tmt.pk
        assert "tmt" not in d  # FK stored as tmt_id, not tmt


class TestComputeDiff:
    """Tests for compute_diff."""

    def test_no_changes(self):
        before = {"a": 1, "b": "hello"}
        after = {"a": 1, "b": "hello"}
        assert compute_diff(before, after) == {}

    def test_scalar_change(self):
        before = {"active": True, "name": "old"}
        after = {"active": False, "name": "old"}
        diff = compute_diff(before, after)
        assert diff == {"active": {"old": True, "new": False}}

    def test_multiple_changes(self):
        before = {"a": 1, "b": 2}
        after = {"a": 10, "b": 20}
        diff = compute_diff(before, after)
        assert "a" in diff
        assert "b" in diff
        assert diff["a"] == {"old": 1, "new": 10}

    def test_dict_nested_diff(self):
        before = {"metadata": {"key1": "val1", "key2": "val2"}}
        after = {"metadata": {"key1": "val1", "key3": "val3"}}
        diff = compute_diff(before, after)
        assert "metadata" in diff
        assert diff["metadata"]["removed"] == {"key2": "val2"}
        assert diff["metadata"]["added"] == {"key3": "val3"}

    def test_dict_changed_values(self):
        before = {"metadata": {"scope": "openid"}}
        after = {"metadata": {"scope": "openid email"}}
        diff = compute_diff(before, after)
        assert diff["metadata"]["changed"] == {"scope": {"old": "openid", "new": "openid email"}}

    def test_new_field(self):
        before = {"a": 1}
        after = {"a": 1, "b": 2}
        diff = compute_diff(before, after)
        assert diff == {"b": {"old": None, "new": 2}}

    def test_removed_field(self):
        before = {"a": 1, "b": 2}
        after = {"a": 1}
        diff = compute_diff(before, after)
        assert diff == {"b": {"old": 2, "new": None}}


# ---------------------------------------------------------------------------
# Event type derivation tests
# ---------------------------------------------------------------------------


class TestEventTypeDerivation:
    """Tests for event type derivation functions."""

    def test_subordinate_revocation(self):
        diff = {"active": {"old": True, "new": False}}
        assert _derive_subordinate_event_type(diff) == "revocation"

    def test_subordinate_metadata_update(self):
        diff = {"metadata": {"changed": {"scope": {"old": "openid", "new": "openid email"}}}}
        assert _derive_subordinate_event_type(diff) == "metadata_update"

    def test_subordinate_forced_metadata_update(self):
        diff = {"forced_metadata": {"added": {"new_key": "new_val"}}}
        assert _derive_subordinate_event_type(diff) == "metadata_policy_update"

    def test_subordinate_jwks_update(self):
        diff = {"jwks": {"old": "old_jwks", "new": "new_jwks"}}
        assert _derive_subordinate_event_type(diff) == "jwks_update"

    def test_subordinate_revocation_takes_priority(self):
        diff = {
            "active": {"old": True, "new": False},
            "metadata": {"changed": {"x": {"old": 1, "new": 2}}},
            "jwks": {"old": "a", "new": "b"},
        }
        assert _derive_subordinate_event_type(diff) == "revocation"

    def test_subordinate_metadata_policy_over_metadata(self):
        diff = {
            "forced_metadata": {"added": {"x": 1}},
            "metadata": {"changed": {"y": {"old": 1, "new": 2}}},
        }
        assert _derive_subordinate_event_type(diff) == "metadata_policy_update"

    def test_subordinate_no_relevant_diff(self):
        diff = {"valid_for": {"old": 100, "new": 200}}
        assert _derive_subordinate_event_type(diff) is None

    def test_subordinate_empty_diff(self):
        assert _derive_subordinate_event_type({}) is None

    def test_trustmarktype_created(self):
        assert _derive_trustmarktype_event_type("CREATE", None) == "trustmarktype_created"

    def test_trustmarktype_deactivated(self):
        diff = {"active": {"old": True, "new": False}}
        assert _derive_trustmarktype_event_type("UPDATE", diff) == "trustmarktype_deactivated"

    def test_trustmarktype_updated(self):
        diff = {"valid_for": {"old": 100, "new": 200}}
        assert _derive_trustmarktype_event_type("UPDATE", diff) == "trustmarktype_updated"

    def test_trustmark_issued(self):
        assert _derive_trustmark_event_type("CREATE", None) == "trustmark_issued"

    def test_trustmark_renewed(self):
        diff = {"mark": {"old": "old_jwt", "new": "new_jwt"}}
        assert _derive_trustmark_event_type("UPDATE", diff, is_renew=True) == "trustmark_renewed"

    def test_trustmark_revoked(self):
        diff = {"active": {"old": True, "new": False}}
        assert _derive_trustmark_event_type("UPDATE", diff) == "trustmark_revoked"

    def test_trustmark_updated(self):
        diff = {"autorenew": {"old": True, "new": False}}
        assert _derive_trustmark_event_type("UPDATE", diff) == "trustmark_updated"


# ---------------------------------------------------------------------------
# Integration tests via API endpoints
# ---------------------------------------------------------------------------


class TestAuditLogIntegration:
    """Integration tests: API operations create AuditLogEntry rows."""

    @pytest.mark.django_db
    def test_create_trustmarktype_logged(self, user):
        """Creating a TrustMarkType creates an audit log entry."""
        from apikeys.models import APIKey

        _, plaintext = APIKey.create_key(name="audit-test", user=user)

        client = Client()
        data = {"tmtype": "https://test.example.com/audit_tmt"}
        response = client.post(
            "/api/v1/trustmarktypes",
            data=json.dumps(data),
            content_type="application/json",
            HTTP_X_API_KEY=plaintext,
        )
        assert response.status_code == 201

        entries = AuditLogEntry.objects.filter(
            resource_type="TrustMarkType",
            action="CREATE",
        )
        assert entries.count() == 1
        entry = entries.first()
        assert entry.user == user
        assert entry.auth_method == "api_key"
        assert entry.success is True
        assert entry.response_code == 201
        assert entry.event_type == "trustmarktype_created"
        assert entry.snapshot_after is not None
        assert entry.snapshot_after["tmtype"] == "https://test.example.com/audit_tmt"

    @pytest.mark.django_db
    def test_update_trustmarktype_logged(self, user):
        """Updating a TrustMarkType creates an audit log entry with diff."""
        from apikeys.models import APIKey
        from trustmarks.models import TrustMarkType

        _, plaintext = APIKey.create_key(name="audit-update-test", user=user)

        tmt = TrustMarkType.objects.create(
            tmtype="https://test.example.com/update_tmt",
            autorenew=True,
            valid_for=8760,
            renewal_time=48,
            active=True,
        )

        client = Client()
        data = {"active": False}
        response = client.put(
            f"/api/v1/trustmarktypes/{tmt.id}",
            data=json.dumps(data),
            content_type="application/json",
            HTTP_X_API_KEY=plaintext,
        )
        assert response.status_code == 200

        entries = AuditLogEntry.objects.filter(
            resource_type="TrustMarkType",
            action="UPDATE",
        )
        assert entries.count() == 1
        entry = entries.first()
        assert entry.event_type == "trustmarktype_deactivated"
        assert entry.diff is not None
        assert entry.diff["active"] == {"old": True, "new": False}
        assert entry.snapshot_before is not None
        assert entry.snapshot_after is not None

    @pytest.mark.django_db
    def test_session_auth_logged(self, auth_client, user):
        """Session-authenticated requests record auth_method='session'."""
        data = {"tmtype": "https://test.example.com/session_audit_tmt"}
        response = auth_client.post(
            "/api/v1/trustmarktypes",
            data=json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code == 201

        entry = AuditLogEntry.objects.filter(
            resource_type="TrustMarkType",
            action="CREATE",
        ).first()
        assert entry is not None
        assert entry.auth_method == "session"
        assert entry.user == user

    @pytest.mark.django_db
    def test_duplicate_trustmarktype_not_logged(self, user):
        """A 403 (already exists) does not create an audit log entry."""
        from apikeys.models import APIKey
        from trustmarks.models import TrustMarkType

        _, plaintext = APIKey.create_key(name="audit-dup-test", user=user)
        TrustMarkType.objects.create(
            tmtype="https://test.example.com/dup_tmt",
            autorenew=True,
            valid_for=8760,
            renewal_time=48,
            active=True,
        )

        client = Client()
        data = {"tmtype": "https://test.example.com/dup_tmt"}
        response = client.post(
            "/api/v1/trustmarktypes",
            data=json.dumps(data),
            content_type="application/json",
            HTTP_X_API_KEY=plaintext,
        )
        assert response.status_code == 403

        assert AuditLogEntry.objects.filter(resource_type="TrustMarkType").count() == 0


class TestAuditLogQueryEndpoint:
    """Tests for the /auditlog query endpoint."""

    @pytest.mark.django_db
    def test_list_audit_log(self, user):
        """Test listing audit log entries."""
        from apikeys.models import APIKey

        _, plaintext = APIKey.create_key(name="audit-query-test", user=user)
        client = Client()

        # Create some entries by making API calls
        data = {"tmtype": "https://test.example.com/query_tmt"}
        client.post(
            "/api/v1/trustmarktypes",
            data=json.dumps(data),
            content_type="application/json",
            HTTP_X_API_KEY=plaintext,
        )

        # Query audit log
        response = client.get(
            "/api/v1/auditlog",
            HTTP_X_API_KEY=plaintext,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) >= 1
        assert items[0]["resource_type"] == "TrustMarkType"

    @pytest.mark.django_db
    def test_filter_by_resource_type(self, user):
        """Test filtering audit log by resource_type."""
        from apikeys.models import APIKey

        _, plaintext = APIKey.create_key(name="audit-filter-test", user=user)
        client = Client()

        # Create two TrustMarkTypes to populate audit log
        client.post(
            "/api/v1/trustmarktypes",
            data=json.dumps({"tmtype": "https://test.example.com/filter_tmt_1"}),
            content_type="application/json",
            HTTP_X_API_KEY=plaintext,
        )
        client.post(
            "/api/v1/trustmarktypes",
            data=json.dumps({"tmtype": "https://test.example.com/filter_tmt_2"}),
            content_type="application/json",
            HTTP_X_API_KEY=plaintext,
        )

        # Filter by TrustMarkType
        response = client.get(
            "/api/v1/auditlog?resource_type=TrustMarkType",
            HTTP_X_API_KEY=plaintext,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) >= 2
        assert all(i["resource_type"] == "TrustMarkType" for i in items)

    @pytest.mark.django_db
    def test_filter_by_action(self, user):
        """Test filtering audit log by action."""
        from apikeys.models import APIKey

        _, plaintext = APIKey.create_key(name="audit-action-test", user=user)
        client = Client()

        response = client.get(
            "/api/v1/auditlog?action=CREATE",
            HTTP_X_API_KEY=plaintext,
        )
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_auditlog_requires_auth(self, db):
        """Test that audit log endpoint requires authentication."""
        client = Client()
        response = client.get("/api/v1/auditlog")
        assert response.status_code == 401

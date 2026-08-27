"""Permanently revoke API keys whenever an owning user's status changes."""

from django.db import migrations


CREATE_REVOCATION_TRIGGER = """
CREATE FUNCTION apikeys_require_active_owner()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM 1
    FROM auth_user
    WHERE id = NEW.user_id AND is_active = TRUE
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'API keys require an active user'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER apikeys_require_active_owner_on_insert
BEFORE INSERT ON apikeys_apikey
FOR EACH ROW
EXECUTE FUNCTION apikeys_require_active_owner();

CREATE TRIGGER apikeys_require_active_owner_on_reassignment
BEFORE UPDATE OF user_id ON apikeys_apikey
FOR EACH ROW
EXECUTE FUNCTION apikeys_require_active_owner();

CREATE FUNCTION apikeys_prevent_key_reactivation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Revoked API keys cannot be reactivated'
        USING ERRCODE = '23514';
END;
$$;

CREATE TRIGGER apikeys_prevent_key_reactivation
BEFORE UPDATE OF is_active ON apikeys_apikey
FOR EACH ROW
WHEN (OLD.is_active = FALSE AND NEW.is_active = TRUE)
EXECUTE FUNCTION apikeys_prevent_key_reactivation();

CREATE FUNCTION apikeys_revoke_on_user_status_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE apikeys_apikey
    SET is_active = FALSE
    WHERE user_id = NEW.id AND is_active = TRUE;
    RETURN NEW;
END;
$$;

CREATE TRIGGER apikeys_revoke_on_user_status_change
AFTER UPDATE OF is_active ON auth_user
FOR EACH ROW
WHEN (OLD.is_active IS DISTINCT FROM NEW.is_active)
EXECUTE FUNCTION apikeys_revoke_on_user_status_change();

-- Permanently revoke keys for accounts that were inactive before this migration.
UPDATE apikeys_apikey AS api_key
SET is_active = FALSE
FROM auth_user AS owner
WHERE api_key.user_id = owner.id
  AND api_key.is_active = TRUE
  AND owner.is_active = FALSE;
"""


DROP_REVOCATION_TRIGGER = """
DROP TRIGGER IF EXISTS apikeys_require_active_owner_on_insert ON apikeys_apikey;
DROP TRIGGER IF EXISTS apikeys_require_active_owner_on_reassignment ON apikeys_apikey;
DROP FUNCTION IF EXISTS apikeys_require_active_owner();
DROP TRIGGER IF EXISTS apikeys_prevent_key_reactivation ON apikeys_apikey;
DROP FUNCTION IF EXISTS apikeys_prevent_key_reactivation();
DROP TRIGGER IF EXISTS apikeys_revoke_on_user_status_change ON auth_user;
DROP FUNCTION IF EXISTS apikeys_revoke_on_user_status_change();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("apikeys", "0002_add_tenant_field"),
    ]

    operations = [
        migrations.RunSQL(
            sql=CREATE_REVOCATION_TRIGGER,
            reverse_sql=DROP_REVOCATION_TRIGGER,
        ),
    ]

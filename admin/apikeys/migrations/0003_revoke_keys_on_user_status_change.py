"""Permanently revoke API keys whenever an owning user's status changes."""

from django.db import migrations


CREATE_REVOCATION_TRIGGER = """
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

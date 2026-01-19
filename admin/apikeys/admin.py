"""Django admin configuration for API Keys."""

from django.contrib import admin, messages
from django.http import HttpRequest
from django.utils.html import format_html

from .models import APIKey


class APIKeyAdmin(admin.ModelAdmin):
    """Admin interface for API Key management."""

    list_display = [
        "name",
        "prefix_display",
        "user",
        "is_active",
        "is_valid_display",
        "created_at",
        "expires_at",
        "last_used_at",
    ]
    list_filter = ["is_active", "created_at", "expires_at"]
    search_fields = ["name", "prefix", "user__username"]
    readonly_fields = ["prefix", "key_hash", "created_at", "last_used_at"]
    ordering = ["-created_at"]

    fieldsets = [
        (
            None,
            {
                "fields": ["name", "user", "is_active"],
            },
        ),
        (
            "Key Information",
            {
                "fields": ["prefix", "key_hash", "created_at", "last_used_at"],
                "classes": ["collapse"],
            },
        ),
        (
            "Expiration",
            {
                "fields": ["expires_at"],
            },
        ),
    ]

    actions = ["revoke_keys"]

    def prefix_display(self, obj: APIKey) -> str:
        """Display the key prefix with ellipsis."""
        return f"{obj.prefix}..."

    prefix_display.short_description = "Key Prefix"  # type: ignore[attr-defined]

    def is_valid_display(self, obj: APIKey) -> str:
        """Display validity status with color."""
        if obj.is_valid:
            return format_html('<span style="color: green;">Valid</span>')
        return format_html('<span style="color: red;">Invalid</span>')

    is_valid_display.short_description = "Status"  # type: ignore[attr-defined]

    @admin.action(description="Revoke selected API keys")
    def revoke_keys(self, request: HttpRequest, queryset) -> None:
        """Revoke (deactivate) selected API keys."""
        count = queryset.update(is_active=False)
        self.message_user(
            request,
            f"Successfully revoked {count} API key(s).",
            messages.SUCCESS,
        )

    def get_readonly_fields(self, request: HttpRequest, obj=None):
        """Make more fields readonly when editing existing key."""
        if obj:  # Editing existing object
            return self.readonly_fields + ["user"]
        return self.readonly_fields

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        """Allow changing API keys."""
        return True

    def save_model(self, request: HttpRequest, obj: APIKey, form, change: bool) -> None:
        """Handle saving - for new keys, generate the key."""
        if not change:  # Creating new key
            # Get form data
            name = form.cleaned_data["name"]
            user = form.cleaned_data["user"]
            expires_at = form.cleaned_data.get("expires_at")

            # Create the key
            api_key, plaintext_key = APIKey.create_key(
                name=name,
                user=user,
                expires_at=expires_at,
            )

            # Show the plaintext key to admin (only time it's visible!)
            self.message_user(
                request,
                format_html(
                    "<strong>API Key created!</strong> "
                    "Copy this key now - it will not be shown again:<br>"
                    '<code style="background: #f0f0f0; padding: 10px; '
                    'display: block; margin: 10px 0; font-size: 14px;">{}</code>',
                    plaintext_key,
                ),
                messages.WARNING,
            )
        else:
            # Just save changes for existing key
            super().save_model(request, obj, form, change)

    def add_view(self, request: HttpRequest, form_url: str = "", extra_context=None):
        """Custom add view - exclude key fields from form."""
        self.exclude = ["prefix", "key_hash"]  # type: ignore[attr-defined]
        return super().add_view(request, form_url, extra_context)

    def change_view(
        self, request: HttpRequest, object_id: str, form_url: str = "", extra_context=None
    ):
        """Custom change view."""
        self.exclude = []  # type: ignore[attr-defined]
        return super().change_view(request, object_id, form_url, extra_context)


admin.site.register(APIKey, APIKeyAdmin)

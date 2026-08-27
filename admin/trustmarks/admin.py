from typing import Any

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from common.claims import validate_trust_mark_additional_claims

from .models import TrustMark, TrustMarkType


class TrustMarkAdminForm(forms.ModelForm):
    """Validate Trust Mark extension claims submitted through Django admin."""

    class Meta:
        model = TrustMark
        fields = "__all__"

    def clean_additional_claims(self) -> dict[str, Any] | None:
        """Reject claims controlled by the Trust Mark issuer."""
        try:
            return validate_trust_mark_additional_claims(self.cleaned_data.get("additional_claims"))
        except ValueError as error:
            raise ValidationError(str(error)) from error


class TrustMarkAdmin(admin.ModelAdmin):
    """Admin configuration for Trust Marks."""

    form = TrustMarkAdminForm


admin.site.register(TrustMarkType)
admin.site.register(TrustMark, TrustMarkAdmin)

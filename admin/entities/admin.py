from typing import Any

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from common.claims import validate_subordinate_additional_claims

from .models import Subordinate


class SubordinateAdminForm(forms.ModelForm):
    """Validate subordinate extension claims submitted through Django admin."""

    class Meta:
        model = Subordinate
        fields = "__all__"

    def clean_additional_claims(self) -> dict[str, Any] | None:
        """Reject claims controlled by the Trust Anchor."""
        try:
            return validate_subordinate_additional_claims(
                self.cleaned_data.get("additional_claims")
            )
        except ValueError as error:
            raise ValidationError(str(error)) from error


class SubordinateAdmin(admin.ModelAdmin):
    """Admin configuration for subordinates."""

    form = SubordinateAdminForm


admin.site.register(Subordinate, SubordinateAdmin)

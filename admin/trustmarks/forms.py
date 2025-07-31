from django import forms

from .models import TrustMarkType


class TrustMarkForm(forms.Form):
    entity = forms.CharField(label="entity")
    tmt_select = forms.ModelChoiceField(queryset=TrustMarkType.objects.all())


class TrustMarkTypeForm(forms.Form):
    type = forms.CharField(label="trust mark type")

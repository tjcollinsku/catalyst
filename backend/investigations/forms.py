from django import forms

from .models import Case, DocumentType


class CaseForm(forms.ModelForm):
    class Meta:
        model = Case
        fields = ["name", "status", "notes", "referral_ref"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


class DocumentUploadForm(forms.Form):
    case = forms.ModelChoiceField(queryset=Case.objects.all(), label="Case")
    file = forms.FileField()
    doc_type = forms.ChoiceField(choices=DocumentType.choices, initial=DocumentType.OTHER)
    source_url = forms.URLField(required=False, label="Source URL (optional)")

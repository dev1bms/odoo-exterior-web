"""Forms for Saved Queries."""

from __future__ import annotations

from django import forms

from audits import data_services
from instances.models import OdooInstance

from .models import SavedQuery


class SavedQueryForm(forms.ModelForm):
    selected_fields_text = forms.CharField(
        label="Selected fields",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "id,display_name,name,write_date",
                "autocomplete": "off",
            }
        ),
        help_text="Comma-separated field names. Unknown fields are ignored when the query runs.",
    )

    class Meta:
        model = SavedQuery
        fields = (
            "name",
            "description",
            "instance",
            "model_name",
            "selected_fields_text",
            "search_field",
            "query",
            "limit",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "model_name": forms.TextInput(attrs={"placeholder": "res.partner"}),
            "search_field": forms.TextInput(attrs={"placeholder": "display_name"}),
            "query": forms.TextInput(attrs={"placeholder": "contains..."}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["instance"].queryset = OdooInstance.objects.filter(user=user).order_by("name")
        self.fields["limit"] = forms.ChoiceField(
            choices=[(n, str(n)) for n in data_services.ALLOWED_LIMITS],
            initial=data_services.DEFAULT_LIMIT,
        )
        self.fields["limit"].help_text = "Maximum number of records to fetch/export."
        self.fields["selected_fields_text"].initial = ",".join(
            self.instance.selected_fields or []
        )
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css)

    def clean_limit(self) -> int:
        return data_services.clamp_limit(self.cleaned_data.get("limit"))

    def clean_selected_fields_text(self) -> list[str]:
        raw = self.cleaned_data.get("selected_fields_text") or ""
        out: list[str] = []
        for item in raw.split(","):
            field = item.strip()
            if field and field not in out:
                out.append(field)
        return out

    def clean(self):
        cleaned = super().clean()
        instance = cleaned.get("instance")
        if instance and instance.user_id != self.user.id:
            self.add_error("instance", "Choose one of your own Odoo instances.")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.user = self.user
        obj.selected_fields = self.cleaned_data.get("selected_fields_text") or []
        obj.limit = data_services.clamp_limit(obj.limit)
        if commit:
            obj.save()
        return obj

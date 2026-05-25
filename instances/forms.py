"""Forms for the instances app."""

from __future__ import annotations

from django import forms

from .models import OdooInstance


class OdooInstanceForm(forms.ModelForm):
    """Create / edit an OdooInstance.

    The plaintext password is captured here and immediately encrypted by
    the view via :py:meth:`OdooInstance.set_password` — it is never saved
    to the model field directly.
    """

    password = forms.CharField(
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}),
        required=False,
        help_text=(
            "Odoo password or API key. Leave blank when editing to keep the "
            "existing value."
        ),
    )

    class Meta:
        model = OdooInstance
        fields = ("name", "odoo_url", "database", "username", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Production"}),
            "odoo_url": forms.URLInput(
                attrs={"placeholder": "https://your-odoo-host.example.com"}
            ),
            "database": forms.TextInput(attrs={"placeholder": "database name"}),
            "username": forms.TextInput(attrs={"placeholder": "audit user login"}),
        }

    def __init__(self, *args, **kwargs):
        self._is_create = kwargs.pop("is_create", True)
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")
        if self._is_create:
            self.fields["password"].required = True

        # Per-field helper copy for the form template.
        self.fields["name"].help_text = (
            "A short label you will recognize in the dashboard, e.g. "
            "<code>Production</code> or <code>Staging</code>."
        )
        self.fields["odoo_url"].help_text = (
            "Base URL of the Odoo instance, including the scheme. "
            "Example: <code>https://your-odoo-host.example.com</code>"
        )
        self.fields["database"].help_text = (
            "Name of the Odoo database to audit (the same value you use on "
            "the Odoo login screen)."
        )
        self.fields["username"].help_text = (
            "Login of the Odoo user that will be used for the audit. "
            "Use a dedicated read-only user when possible."
        )
        self.fields["is_active"].help_text = (
            "Inactive instances are kept in your dashboard but cannot run new audits."
        )

    def clean_odoo_url(self) -> str:
        url = (self.cleaned_data.get("odoo_url") or "").strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise forms.ValidationError(
                "URL must start with 'http://' or 'https://'."
            )
        return url

"""Models for reusable Data Explorer query configurations."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from audits import data_services


def _default_fields() -> list[str]:
    return []


class SavedQuery(models.Model):
    """A reusable, read-only Data Explorer configuration.

    This stores query *settings* only: never exported data and never Odoo
    credentials. Ownership is explicit via ``user`` and reinforced in forms
    and views by requiring ``instance.user == user``.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_queries",
    )
    instance = models.ForeignKey(
        "instances.OdooInstance",
        on_delete=models.CASCADE,
        related_name="saved_queries",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    model_name = models.CharField(max_length=255)
    selected_fields = models.JSONField(default=_default_fields, blank=True)
    search_field = models.CharField(max_length=255, blank=True, default="")
    query = models.CharField(max_length=255, blank=True, default="")
    limit = models.PositiveIntegerField(default=data_services.DEFAULT_LIMIT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_run_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-updated_at", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "name"),
                name="unique_saved_query_name_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.model_name})"

    def clean(self) -> None:
        super().clean()
        if self.instance_id and self.user_id and self.instance.user_id != self.user_id:
            raise ValidationError("Saved query instance must belong to the same user.")
        self.limit = data_services.clamp_limit(self.limit)
        if not isinstance(self.selected_fields, list):
            raise ValidationError({"selected_fields": "Selected fields must be a list."})
        self.selected_fields = [
            str(field).strip()
            for field in self.selected_fields
            if str(field).strip()
        ]

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("saved_queries:detail", kwargs={"pk": self.pk})

    @property
    def field_count(self) -> int:
        return len(self.selected_fields or [])

    @property
    def search_summary(self) -> str:
        if self.search_field and self.query:
            return f"{self.search_field} contains {self.query}"
        return "—"

"""App config for saved Data Explorer queries."""

from __future__ import annotations

from django.apps import AppConfig


class SavedQueriesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "saved_queries"
    verbose_name = "Saved Queries"

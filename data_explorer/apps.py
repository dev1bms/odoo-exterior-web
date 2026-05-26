"""App config for the top-level Data Explorer."""

from __future__ import annotations

from django.apps import AppConfig


class DataExplorerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "data_explorer"
    verbose_name = "Data Explorer"

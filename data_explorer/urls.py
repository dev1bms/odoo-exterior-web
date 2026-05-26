"""URL configuration for the top-level Data Explorer.

The pattern order matters: ``<path:model_name>`` is greedy, so the
export route MUST be registered before the model browse route — same
trick we use in ``audits/urls.py``.
"""

from __future__ import annotations

from django.urls import path

from .views import (
    DataExplorerExportView,
    DataExplorerIndexView,
    DataExplorerInstanceView,
    DataExplorerModelView,
)


urlpatterns = [
    path("", DataExplorerIndexView.as_view(), name="index"),
    path(
        "instance/<int:instance_id>/",
        DataExplorerInstanceView.as_view(),
        name="instance",
    ),
    # Export route first — its tail (`/export/<format>/`) is more specific.
    path(
        "instance/<int:instance_id>/model/<path:model_name>/export/<str:format>/",
        DataExplorerExportView.as_view(),
        name="export",
    ),
    path(
        "instance/<int:instance_id>/model/<path:model_name>/",
        DataExplorerModelView.as_view(),
        name="model",
    ),
]

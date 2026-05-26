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
    DataExplorerViewJsonView,
)


urlpatterns = [
    path("", DataExplorerIndexView.as_view(), name="index"),
    path(
        "instance/<int:instance_id>/",
        DataExplorerInstanceView.as_view(),
        name="instance",
    ),
    path(
        "instance/<int:instance_id>/model/<path:model_name>/view/json/",
        DataExplorerViewJsonView.as_view(),
        name="view_json",
    ),
    # Export route before model browse — tail (`/export/<format>/`) is specific.
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

"""URL configuration for the audits app."""

from __future__ import annotations

from django.urls import path

from .viewer_views import (
    ViewAuditJsonView,
    ViewAuditMarkdownView,
    ViewCategoryJsonView,
    ViewCategoryMarkdownView,
    ViewModelDataJsonView,
    ViewModelJsonView,
    ViewModelMarkdownView,
)
from .views import (
    AuditDetailView,
    AuditExplorerView,
    AuditModelDataView,
    AuditModelDetailView,
    DownloadJsonView,
    DownloadMarkdownView,
    ExportCategoryView,
    ExportModelDataView,
    ExportModelDetailView,
    RunAuditView,
)


urlpatterns = [
    path("run/<int:instance_pk>/", RunAuditView.as_view(), name="run"),
    path("<int:pk>/", AuditDetailView.as_view(), name="detail"),
    path("<int:pk>/view/json/", ViewAuditJsonView.as_view(), name="view_audit_json"),
    path(
        "<int:pk>/view/markdown/",
        ViewAuditMarkdownView.as_view(),
        name="view_audit_markdown",
    ),
    path(
        "<int:pk>/view/<str:category>/json/",
        ViewCategoryJsonView.as_view(),
        name="view_category_json",
    ),
    path(
        "<int:pk>/view/<str:category>/markdown/",
        ViewCategoryMarkdownView.as_view(),
        name="view_category_markdown",
    ),
    path("<int:pk>/markdown/", DownloadMarkdownView.as_view(), name="download_markdown"),
    path("<int:pk>/json/", DownloadJsonView.as_view(), name="download_json"),
    path(
        "<int:pk>/explorer/<str:category>/",
        AuditExplorerView.as_view(),
        name="explorer",
    ),
    path(
        "<int:pk>/export/<str:category>/<str:format>/",
        ExportCategoryView.as_view(),
        name="export_category",
    ),
    # Model Data Explorer (live Odoo records, read-only). Registered
    # before the model-detail patterns so the greedy ``<path:model_name>``
    # of those routes cannot swallow the trailing ``/data/...`` segment.
    path(
        "<int:pk>/models/<path:model_name>/data/view/json/",
        ViewModelDataJsonView.as_view(),
        name="view_model_data_json",
    ),
    path(
        "<int:pk>/models/<path:model_name>/data/export/<str:format>/",
        ExportModelDataView.as_view(),
        name="export_model_data",
    ),
    path(
        "<int:pk>/models/<path:model_name>/data/",
        AuditModelDataView.as_view(),
        name="model_data_explorer",
    ),
    # Model drill-down. The export pattern must be registered BEFORE the
    # detail pattern because ``<path:model_name>`` is greedy and would
    # otherwise swallow the trailing ``/export/<format>/`` segment.
    path(
        "<int:pk>/models/<path:model_name>/view/json/",
        ViewModelJsonView.as_view(),
        name="view_model_json",
    ),
    path(
        "<int:pk>/models/<path:model_name>/view/markdown/",
        ViewModelMarkdownView.as_view(),
        name="view_model_markdown",
    ),
    path(
        "<int:pk>/models/<path:model_name>/export/<str:format>/",
        ExportModelDetailView.as_view(),
        name="export_model_detail",
    ),
    path(
        "<int:pk>/models/<path:model_name>/",
        AuditModelDetailView.as_view(),
        name="model_detail",
    ),
]

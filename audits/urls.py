"""URL configuration for the audits app."""

from __future__ import annotations

from django.urls import path

from .views import AuditDetailView, DownloadJsonView, DownloadMarkdownView, RunAuditView


urlpatterns = [
    path("run/<int:instance_pk>/", RunAuditView.as_view(), name="run"),
    path("<int:pk>/", AuditDetailView.as_view(), name="detail"),
    path("<int:pk>/markdown/", DownloadMarkdownView.as_view(), name="download_markdown"),
    path("<int:pk>/json/", DownloadJsonView.as_view(), name="download_json"),
]

"""URL configuration for Saved Queries."""

from __future__ import annotations

from django.urls import path

from .views import (
    SavedQueryCreateView,
    SavedQueryDeleteView,
    SavedQueryDetailView,
    SavedQueryExportView,
    SavedQueryListView,
    SavedQueryRunView,
    SavedQueryUpdateView,
)


urlpatterns = [
    path("", SavedQueryListView.as_view(), name="list"),
    path("new/", SavedQueryCreateView.as_view(), name="create"),
    path("<int:pk>/", SavedQueryDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", SavedQueryUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", SavedQueryDeleteView.as_view(), name="delete"),
    path("<int:pk>/run/", SavedQueryRunView.as_view(), name="run"),
    path("<int:pk>/export/<str:format>/", SavedQueryExportView.as_view(), name="export"),
]

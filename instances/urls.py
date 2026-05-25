"""URL configuration for the instances app."""

from __future__ import annotations

from django.urls import path

from .views import (
    DashboardView,
    InstanceCreateView,
    InstanceDeleteView,
    InstanceDetailView,
    InstanceUpdateView,
    TestConnectionView,
)


urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("new/", InstanceCreateView.as_view(), name="create"),
    path("<int:pk>/", InstanceDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", InstanceUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", InstanceDeleteView.as_view(), name="delete"),
    path("<int:pk>/test/", TestConnectionView.as_view(), name="test"),
]

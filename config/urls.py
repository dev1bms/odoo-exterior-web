"""Top-level URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", TemplateView.as_view(template_name="landing.html"), name="landing"),
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
    path("instances/", include(("instances.urls", "instances"), namespace="instances")),
    path("audits/", include(("audits.urls", "audits"), namespace="audits")),
    path(
        "data-explorer/",
        include(("data_explorer.urls", "data_explorer"), namespace="data_explorer"),
    ),
]

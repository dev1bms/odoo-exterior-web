"""URL configuration for the accounts app."""

from __future__ import annotations

from django.urls import path

from .views import AppLoginView, AppLogoutView, RegisterView


urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", AppLoginView.as_view(), name="login"),
    path("logout/", AppLogoutView.as_view(), name="logout"),
]

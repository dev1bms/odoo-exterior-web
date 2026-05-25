"""Views for the accounts app."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import CreateView

from .forms import RegistrationForm


class RegisterView(CreateView):
    """Register a new user, then log them in."""

    form_class = RegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("instances:dashboard")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(
            self.request,
            "Welcome to odoo-exterior-web. Add your first Odoo instance below.",
        )
        return response


class AppLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class AppLogoutView(LogoutView):
    """Standard logout; redirects to LOGOUT_REDIRECT_URL."""

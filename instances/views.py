"""Views for the instances app."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import OdooInstanceForm
from .models import OdooInstance


class OwnerQuerysetMixin(LoginRequiredMixin):
    """Limit any queryset to the current user's records."""

    model = OdooInstance

    def get_queryset(self):  # type: ignore[override]
        return OdooInstance.objects.filter(user=self.request.user)


class DashboardView(OwnerQuerysetMixin, ListView):
    """The main dashboard: list of the user's Odoo instances + recent audits."""

    template_name = "instances/dashboard.html"
    context_object_name = "instances"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Avoid a hard import cycle: import here.
        from audits.models import AuditRun

        user = self.request.user
        user_audits = AuditRun.objects.filter(instance__user=user)

        ctx["recent_audits"] = (
            user_audits
            .select_related("instance")
            .order_by("-created_at")[:10]
        )
        ctx["stats"] = {
            "instance_count": ctx["instances"].count(),
            "completed_count": user_audits.filter(
                status=AuditRun.Status.COMPLETED
            ).count(),
            "failed_count": user_audits.filter(
                status=AuditRun.Status.FAILED
            ).count(),
            "latest_audit": user_audits.order_by("-created_at").first(),
        }
        return ctx


class InstanceDetailView(OwnerQuerysetMixin, DetailView):
    template_name = "instances/instance_detail.html"
    context_object_name = "instance"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from audits.models import AuditRun
        audits = AuditRun.objects.filter(instance=self.object).order_by("-created_at")
        ctx["audits"] = audits
        ctx["latest_audit"] = audits.first()
        ctx["latest_completed_audit"] = (
            audits.filter(status=AuditRun.Status.COMPLETED).first()
        )
        return ctx


class InstanceCreateView(LoginRequiredMixin, CreateView):
    model = OdooInstance
    form_class = OdooInstanceForm
    template_name = "instances/instance_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["is_create"] = True
        return kwargs

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.user = self.request.user
        self.object.set_password(form.cleaned_data["password"])
        self.object.save()
        messages.success(
            self.request,
            f"Instance '{self.object.name}' was added. "
            "You can now test the connection and run an audit.",
        )
        return redirect(self.object.get_absolute_url())


class InstanceUpdateView(OwnerQuerysetMixin, UpdateView):
    form_class = OdooInstanceForm
    template_name = "instances/instance_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["is_create"] = False
        return kwargs

    def form_valid(self, form):
        self.object = form.save(commit=False)
        new_password = form.cleaned_data.get("password")
        if new_password:
            self.object.set_password(new_password)
        self.object.save()
        messages.success(self.request, "Instance updated.")
        return redirect(self.object.get_absolute_url())


class InstanceDeleteView(OwnerQuerysetMixin, DeleteView):
    template_name = "instances/instance_confirm_delete.html"
    success_url = reverse_lazy("instances:dashboard")

    def form_valid(self, form):
        messages.info(self.request, f"Instance '{self.object.name}' deleted.")
        return super().form_valid(form)


class TestConnectionView(LoginRequiredMixin, View):
    """POST-only endpoint that triggers an authentication check."""

    def post(self, request, pk: int):
        instance = get_object_or_404(OdooInstance, pk=pk, user=request.user)
        # Lazy import to avoid loading the extractor on app startup.
        from audits.services import test_odoo_connection

        ok, error = test_odoo_connection(instance)
        if ok:
            messages.success(request, "Connection successful.")
        else:
            messages.error(request, f"Connection failed: {error}")
        return redirect(instance.get_absolute_url())

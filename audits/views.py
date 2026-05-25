"""Views for the audits app."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView

from instances.models import OdooInstance

from .models import AuditRun


class _OwnedAuditMixin(LoginRequiredMixin):
    """Restrict access so users only see audits of their own instances."""

    model = AuditRun

    def get_queryset(self):  # type: ignore[override]
        return AuditRun.objects.filter(instance__user=self.request.user).select_related(
            "instance"
        )


class AuditDetailView(_OwnedAuditMixin, DetailView):
    template_name = "audits/audit_detail.html"
    context_object_name = "audit"


class RunAuditView(LoginRequiredMixin, View):
    """POST-only endpoint that synchronously runs a Studio audit."""

    def post(self, request, instance_pk: int):
        instance = get_object_or_404(
            OdooInstance, pk=instance_pk, user=request.user
        )
        # Lazy import to avoid loading the extractor on app startup.
        from .services import run_studio_audit

        run = run_studio_audit(instance)
        if run.status == AuditRun.Status.COMPLETED:
            messages.success(
                request,
                f"Audit #{run.pk} completed in "
                f"{run.duration_seconds:.1f}s." if run.duration_seconds is not None
                else f"Audit #{run.pk} completed.",
            )
        else:
            messages.error(
                request,
                f"Audit #{run.pk} failed: {run.error_message or 'see details below.'}",
            )
        return redirect(run.get_absolute_url())


class DownloadMarkdownView(_OwnedAuditMixin, View):
    """Serve the Markdown report as an attachment."""

    def get(self, request, pk: int):
        audit = get_object_or_404(self.get_queryset(), pk=pk)
        if not audit.markdown_report:
            messages.warning(request, "This audit has no Markdown report.")
            return redirect(audit.get_absolute_url())
        response = HttpResponse(
            audit.markdown_report, content_type="text/markdown; charset=utf-8"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="studio_report_{audit.pk}.md"'
        )
        return response


class DownloadJsonView(_OwnedAuditMixin, View):
    """Serve the raw JSON dataset as an attachment."""

    def get(self, request, pk: int):
        audit = get_object_or_404(self.get_queryset(), pk=pk)
        if not audit.json_report:
            messages.warning(request, "This audit has no JSON report.")
            return redirect(audit.get_absolute_url())
        payload = json.dumps(
            audit.json_report, indent=2, ensure_ascii=False, default=str
        )
        response = HttpResponse(payload, content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="studio_data_{audit.pk}.json"'
        )
        return response

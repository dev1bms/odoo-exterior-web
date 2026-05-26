"""Views for the audits app."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView

from instances.models import OdooInstance

from . import data_services, explorer
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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["category_cards"] = explorer.build_category_cards(self.object)
        return ctx


class AuditExplorerView(_OwnedAuditMixin, DetailView):
    """Per-category browsable table backed by ``audit.json_report``."""

    template_name = "audits/audit_category_explorer.html"
    context_object_name = "audit"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        category = self.kwargs["category"]
        cfg = explorer.get_category_config(category)
        if cfg is None:
            raise Http404(f"Unknown audit category: {category!r}")

        records = explorer.get_category_records(self.object, category)
        columns = cfg["columns"]
        rows = explorer.build_rows(records, columns)

        # For the "models" category, pre-resolve the technical name of each
        # row so the template can render the drill-down link without
        # touching potentially-missing dict keys (which would raise
        # ``VariableDoesNotExist`` in templates).
        if category == "models":
            drill_targets = [
                explorer.get_model_identifier(rec) or "" for rec in records
            ]
        else:
            drill_targets = [""] * len(records)

        ctx.update(
            {
                "category": category,
                "category_config": cfg,
                "columns": columns,
                "records": records,
                "rows": rows,
                "record_rows": list(zip(records, rows, drill_targets)),
                "count": len(records),
                "export_formats": explorer.EXPORT_FORMATS,
            }
        )
        return ctx


class ExportCategoryView(_OwnedAuditMixin, View):
    """Download a single category as JSON, CSV, or Markdown."""

    def get(self, request, pk: int, category: str, format: str):
        if format not in explorer.EXPORT_FORMATS:
            raise Http404(f"Unsupported export format: {format!r}")
        cfg = explorer.get_category_config(category)
        if cfg is None:
            raise Http404(f"Unknown audit category: {category!r}")

        audit = get_object_or_404(self.get_queryset(), pk=pk)
        records = explorer.get_category_records(audit, category)
        filename_stem = f"audit_{audit.pk}_{category}"

        if format == "json":
            body = explorer.records_to_json(records)
            return _attachment(body, "application/json", f"{filename_stem}.json")
        if format == "csv":
            body = explorer.records_to_csv(records, cfg["columns"])
            return _attachment(body, "text/csv", f"{filename_stem}.csv")
        # markdown
        body = explorer.records_to_markdown(audit, category, records)
        return _attachment(body, "text/markdown", f"{filename_stem}.md")


class AuditModelDetailView(_OwnedAuditMixin, DetailView):
    """Per-model drill-down profile (fields, views, security, relationships)."""

    template_name = "audits/audit_model_detail.html"
    context_object_name = "audit"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        model_name = self.kwargs["model_name"]
        payload = explorer.build_model_detail_payload(self.object, model_name)
        if payload is None:
            raise Http404(
                f"Model {model_name!r} is not present in audit "
                f"#{self.object.pk}."
            )
        ctx.update(
            {
                "model_name": model_name,
                "payload": payload,
                "model_record": payload["model_record"],
                "summary": payload["summary"],
                "metric_cards": explorer.build_model_detail_metric_cards(payload),
                "sections": explorer.build_model_detail_section_rows(payload),
                "fields": payload["fields"],
                "views": payload["views"],
                "server_actions": payload["server_actions"],
                "window_actions": payload["window_actions"],
                "menus": payload["menus"],
                "access_rights": payload["access_rights"],
                "record_rules": payload["record_rules"],
                "relationships": payload["relationships"],
                "model_export_formats": explorer.MODEL_EXPORT_FORMATS,
                "raw_payload_json": explorer.model_detail_to_json(payload),
            }
        )
        return ctx


class ExportModelDetailView(_OwnedAuditMixin, View):
    """Download a single model's drill-down profile as JSON or Markdown."""

    def get(self, request, pk: int, model_name: str, format: str):
        if format not in explorer.MODEL_EXPORT_FORMATS:
            raise Http404(f"Unsupported export format: {format!r}")
        audit = get_object_or_404(self.get_queryset(), pk=pk)
        payload = explorer.build_model_detail_payload(audit, model_name)
        if payload is None:
            raise Http404(f"Model {model_name!r} not in audit.")

        stem = f"audit_{audit.pk}_model_{explorer.safe_model_filename(model_name)}"
        if format == "json":
            return _attachment(
                explorer.model_detail_to_json(payload),
                "application/json",
                f"{stem}.json",
            )
        # markdown
        return _attachment(
            explorer.model_detail_to_markdown(audit, model_name, payload),
            "text/markdown",
            f"{stem}.md",
        )


def _attachment(body: str, content_type: str, filename: str) -> HttpResponse:
    """Return an ``attachment`` HTTP response with the right content type."""
    response = HttpResponse(body, content_type=f"{content_type}; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# --------------------------------------------------------------------- #
# Model Data Explorer — live Odoo records browsing & export
# --------------------------------------------------------------------- #

class _ModelDataMixin(_OwnedAuditMixin):
    """Shared validation for the Data Explorer page + its export endpoint.

    Loads the audit (with ownership scoping), confirms the requested model
    exists in the audit's JSON, then delegates *all* query-param parsing,
    field allowlisting, live fetching and row rendering to
    :func:`data_services.build_data_explorer_context` so that the
    top-level Data Explorer (the ``data_explorer`` app) can reuse the
    exact same business logic.
    """

    def _load(self, request, pk: int, model_name: str):
        audit = get_object_or_404(self.get_queryset(), pk=pk)
        # The model must exist in the audit JSON. Never trust the URL.
        if data_services.validate_model_in_audit(audit, model_name) is None:
            raise Http404(f"Model {model_name!r} not in audit.")
        return data_services.build_data_explorer_context(request, audit, model_name)


class AuditModelDataView(_ModelDataMixin, View):
    """Browse live Odoo records for one model (read-only, paginated)."""

    template_name = "audits/audit_model_data.html"

    def get(self, request, pk: int, model_name: str):
        ctx = self._load(request, pk, model_name)
        from django.template.response import TemplateResponse
        return TemplateResponse(request, self.template_name, ctx)


class ExportModelDataView(_ModelDataMixin, View):
    """Export the *currently filtered* Data Explorer result as JSON or CSV."""

    def get(self, request, pk: int, model_name: str, format: str):
        if format not in data_services.DATA_EXPORT_FORMATS:
            raise Http404(f"Unsupported export format: {format!r}")

        ctx = self._load(request, pk, model_name)
        result = ctx["result"]
        # If the live fetch errored, surface it as a 502-ish plain text body
        # rather than serving an empty/garbled file.
        if not result.ok:
            return HttpResponse(
                f"Could not fetch data: {result.error}\n",
                content_type="text/plain; charset=utf-8",
                status=502,
            )

        stem = data_services.export_filename_stem(ctx["audit"], model_name)
        if format == "json":
            return _attachment(
                data_services.records_to_json(result.records),
                "application/json",
                f"{stem}.json",
            )
        # csv
        return _attachment(
            data_services.records_to_csv(result.records, ctx["fields_used"]),
            "text/csv",
            f"{stem}.csv",
        )


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

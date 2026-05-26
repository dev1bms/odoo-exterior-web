"""Views for Saved Queries."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from audits import data_services

from .forms import SavedQueryForm
from .models import SavedQuery


class OwnerQuerysetMixin(LoginRequiredMixin):
    model = SavedQuery

    def get_queryset(self):  # type: ignore[override]
        return (
            SavedQuery.objects
            .filter(user=self.request.user)
            .select_related("instance")
        )


class SavedQueryListView(OwnerQuerysetMixin, ListView):
    template_name = "saved_queries/list.html"
    context_object_name = "saved_queries"


class SavedQueryDetailView(OwnerQuerysetMixin, DetailView):
    template_name = "saved_queries/detail.html"
    context_object_name = "saved_query"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        latest = data_services.get_latest_completed_audit_for_instance(self.object.instance)
        ctx["latest_audit"] = latest
        ctx["model_exists"] = bool(
            latest and data_services.validate_model_in_audit(latest, self.object.model_name)
        )
        return ctx


class SavedQueryCreateView(LoginRequiredMixin, CreateView):
    model = SavedQuery
    form_class = SavedQueryForm
    template_name = "saved_queries/form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET:
            initial.update(
                {
                    "instance": self.request.GET.get("instance") or None,
                    "model_name": self.request.GET.get("model_name", ""),
                    "selected_fields_text": self.request.GET.get("fields", ""),
                    "search_field": self.request.GET.get("search_field", ""),
                    "query": self.request.GET.get("q", ""),
                    "limit": data_services.clamp_limit(self.request.GET.get("limit")),
                }
            )
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Saved query created.")
        return super().form_valid(form)


class SavedQueryUpdateView(OwnerQuerysetMixin, UpdateView):
    form_class = SavedQueryForm
    template_name = "saved_queries/form.html"
    context_object_name = "saved_query"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Saved query updated.")
        return super().form_valid(form)


class SavedQueryDeleteView(OwnerQuerysetMixin, DeleteView):
    template_name = "saved_queries/confirm_delete.html"
    context_object_name = "saved_query"
    success_url = reverse_lazy("saved_queries:list")

    def form_valid(self, form):
        messages.info(self.request, f"Saved query '{self.object.name}' deleted.")
        return super().form_valid(form)


class SavedQueryRunView(OwnerQuerysetMixin, View):
    template_name = "saved_queries/run.html"

    def get(self, request, pk: int):
        saved_query = get_object_or_404(self.get_queryset(), pk=pk)
        ctx = build_saved_query_result_context(saved_query)
        saved_query.last_run_at = timezone.now()
        saved_query.save(update_fields=["last_run_at", "updated_at"])
        return TemplateResponse(request, self.template_name, ctx)


class SavedQueryExportView(OwnerQuerysetMixin, View):
    def get(self, request, pk: int, format: str):
        if format not in data_services.DATA_EXPORT_FORMATS:
            raise Http404(f"Unsupported export format: {format!r}")
        saved_query = get_object_or_404(self.get_queryset(), pk=pk)
        ctx = build_saved_query_result_context(saved_query)
        result = ctx["result"]
        if not result.ok:
            return HttpResponse(
                f"Could not fetch data: {result.error}\n",
                content_type="text/plain; charset=utf-8",
                status=502,
            )
        saved_query.last_run_at = timezone.now()
        saved_query.save(update_fields=["last_run_at", "updated_at"])
        stem = f"saved_query_{saved_query.pk}_{data_services.export_filename_stem(ctx['audit'], saved_query.model_name)}"
        if format == "json":
            return _attachment(
                data_services.records_to_json(result.records),
                "application/json",
                f"{stem}.json",
            )
        return _attachment(
            data_services.records_to_csv(result.records, ctx["fields_used"]),
            "text/csv",
            f"{stem}.csv",
        )


def build_saved_query_result_context(saved_query: SavedQuery) -> dict[str, Any]:
    audit = data_services.get_latest_completed_audit_for_instance(saved_query.instance)
    if audit is None:
        return {
            "saved_query": saved_query,
            "audit": None,
            "instance": saved_query.instance,
            "model_name": saved_query.model_name,
            "available_fields": [],
            "fields_used": saved_query.selected_fields or [],
            "rows": [],
            "allowed_limits": data_services.ALLOWED_LIMITS,
            "result": data_services.FetchResult(
                fields_used=saved_query.selected_fields or [],
                error="Run a Studio Audit first to build the model and field catalog used by Saved Queries.",
            ),
        }
    if data_services.validate_model_in_audit(audit, saved_query.model_name) is None:
        raise Http404(f"Model {saved_query.model_name!r} is not part of audit #{audit.pk}.")

    available = data_services.get_model_available_fields(audit, saved_query.model_name)
    defaults = data_services.get_default_data_fields(audit, saved_query.model_name)
    fields_used = data_services.sanitize_field_selection(
        saved_query.selected_fields or [],
        available,
        defaults=defaults,
    )
    search_field = data_services.sanitize_search_field(saved_query.search_field, available)
    limit = data_services.clamp_limit(saved_query.limit)
    result = data_services.fetch_model_records(
        audit,
        saved_query.model_name,
        fields=fields_used,
        limit=limit,
        offset=0,
        search_field=search_field,
        query=saved_query.query,
    )
    rows = data_services.build_data_rows(result.records, result.fields_used, available)
    return {
        "saved_query": saved_query,
        "audit": audit,
        "instance": saved_query.instance,
        "model_name": saved_query.model_name,
        "model_record": data_services.validate_model_in_audit(audit, saved_query.model_name) or {},
        "available_fields": available,
        "fields_used": result.fields_used,
        "search_field": search_field,
        "query": saved_query.query,
        "limit": limit,
        "offset": 0,
        "rows": rows,
        "result": result,
        "allowed_limits": data_services.ALLOWED_LIMITS,
        "showing_from": 1 if result.records else 0,
        "showing_to": len(result.records),
    }


def _attachment(body: str, content_type: str, filename: str) -> HttpResponse:
    response = HttpResponse(body, content_type=f"{content_type}; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

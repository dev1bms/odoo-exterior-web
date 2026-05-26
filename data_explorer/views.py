"""Top-level Data Explorer views.

This app *productizes* the existing model-scoped Data Explorer
(``/audits/<id>/models/<model_name>/data/``) by:

* exposing a Data Explorer landing page driven by the user's instances,
* picking the latest *completed* audit per instance as the metadata
  catalog (models / fields the user is allowed to browse / export),
* delegating the live read-only fetch + serialization to the existing
  :mod:`audits.data_services` helpers — no business logic is duplicated.

Security & invariants enforced here:

* every view is ``LoginRequiredMixin``,
* ``OdooInstance`` lookups are scoped by ``user=request.user``,
* ``model_name`` from the URL is validated against the *latest completed
  audit's* ``json_report["models"]``; tampered URLs return 404,
* export formats are constrained to the values declared in
  ``data_services.DATA_EXPORT_FORMATS`` (``json`` / ``csv``),
* limits are clamped inside ``build_data_explorer_context`` (max 1000),
* credentials are only ever read inside the data-services layer through
  ``OdooInstance.get_password()`` and are never templated or logged.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.views import View

from audits import data_services, viewer_utils
from audits.models import AuditRun
from instances.models import OdooInstance


# --------------------------------------------------------------------- #
# Shared mixin: scoped instance lookup + latest-completed-audit
# --------------------------------------------------------------------- #

class _OwnedInstanceMixin(LoginRequiredMixin):
    """Only let users see / browse Odoo instances they own."""

    def _get_instance(self, instance_id: int) -> OdooInstance:
        return get_object_or_404(
            OdooInstance,
            pk=instance_id,
            user=self.request.user,
        )

    @staticmethod
    def _latest_completed_audit(instance: OdooInstance) -> AuditRun | None:
        return data_services.get_latest_completed_audit_for_instance(instance)


# --------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------- #

class DataExplorerIndexView(_OwnedInstanceMixin, View):
    """Landing page: pick an Odoo instance to explore."""

    template_name = "data_explorer/index.html"

    def get(self, request):
        instances = OdooInstance.objects.filter(user=request.user).order_by("name")

        # Build a per-instance summary so the template stays declarative.
        rows: list[dict[str, Any]] = []
        for inst in instances:
            latest = self._latest_completed_audit(inst)
            model_count = 0
            if latest:
                models = (latest.json_report or {}).get("models")
                model_count = len(models) if isinstance(models, list) else 0
            rows.append(
                {
                    "instance": inst,
                    "latest_audit": latest,
                    "model_count": model_count,
                }
            )

        ctx = {"rows": rows}
        return TemplateResponse(request, self.template_name, ctx)


class DataExplorerInstanceView(_OwnedInstanceMixin, View):
    """Per-instance model catalog (driven by the latest completed audit)."""

    template_name = "data_explorer/instance.html"

    # Quick-link technical names. The template only renders the ones that
    # actually exist in the chosen audit, so we never link to a model the
    # user hasn't audited.
    QUICK_LINKS: tuple[str, ...] = (
        "res.partner",
        "product.template",
        "account.move",
        "x_dashboard",
    )

    def get(self, request, instance_id: int):
        instance = self._get_instance(instance_id)
        latest = self._latest_completed_audit(instance)

        ctx: dict[str, Any] = {
            "instance": instance,
            "latest_audit": latest,
            "models": [],
            "model_count": 0,
            "quick_links": [],
        }

        if latest:
            raw_models = (latest.json_report or {}).get("models") or []
            fields_by_model = self._fields_per_model(latest)
            relations_by_model = self._relations_per_model(latest)

            models: list[dict[str, Any]] = []
            for m in raw_models:
                if not isinstance(m, dict):
                    continue
                name = m.get("model") or m.get("technical_name") or m.get("name")
                if not isinstance(name, str) or not name:
                    continue
                models.append(
                    {
                        "model": name,
                        "name": m.get("name") or "",
                        "state": m.get("state") or "",
                        "transient": bool(m.get("transient")),
                        "field_count": fields_by_model.get(name, 0),
                        "relation_count": relations_by_model.get(name, 0),
                    }
                )
            models.sort(key=lambda r: r["model"])

            present = {m["model"] for m in models}
            quick = [name for name in self.QUICK_LINKS if name in present]

            ctx.update(
                {
                    "models": models,
                    "model_count": len(models),
                    "quick_links": quick,
                }
            )

        return TemplateResponse(request, self.template_name, ctx)

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _fields_per_model(audit: AuditRun) -> dict[str, int]:
        """Count fields per model from the audit JSON."""
        out: dict[str, int] = {}
        for f in (audit.json_report or {}).get("fields") or []:
            if not isinstance(f, dict):
                continue
            m = f.get("model")
            if isinstance(m, str) and m:
                out[m] = out.get(m, 0) + 1
        return out

    @staticmethod
    def _relations_per_model(audit: AuditRun) -> dict[str, int]:
        """Count relational fields (m2o / m2m / o2m) per model."""
        out: dict[str, int] = {}
        relational = {"many2one", "many2many", "one2many"}
        for f in (audit.json_report or {}).get("fields") or []:
            if not isinstance(f, dict):
                continue
            m = f.get("model")
            ttype = f.get("ttype")
            if isinstance(m, str) and m and ttype in relational:
                out[m] = out.get(m, 0) + 1
        return out


class _ModelEntryMixin(_OwnedInstanceMixin):
    """Shared resolver: instance -> latest audit -> model validation."""

    def _resolve(self, instance_id: int, model_name: str):
        instance = self._get_instance(instance_id)
        latest = self._latest_completed_audit(instance)
        if latest is None:
            # No catalog -> can't browse anything.
            raise Http404(
                "No completed audit found for this instance. "
                "Run a Studio audit first."
            )
        if data_services.validate_model_in_audit(latest, model_name) is None:
            raise Http404(f"Model {model_name!r} is not part of audit #{latest.pk}.")
        return instance, latest


class DataExplorerModelView(_ModelEntryMixin, View):
    """Browse live records for one model, using the latest audit's catalog."""

    template_name = "data_explorer/model.html"

    def get(self, request, instance_id: int, model_name: str):
        instance, latest = self._resolve(instance_id, model_name)
        ctx = data_services.build_data_explorer_context(request, latest, model_name)
        # Override the instance so the template doesn't have to reach into
        # ``audit.instance`` (it's the same object, but this keeps the
        # template's mental model crisp).
        ctx["instance"] = instance
        return TemplateResponse(request, self.template_name, ctx)


class DataExplorerViewJsonView(_ModelEntryMixin, View):
    """In-browser JSON view of the current Data Explorer slice."""

    template_name = "audits/view_json.html"

    def get(self, request, instance_id: int, model_name: str):
        instance, latest = self._resolve(instance_id, model_name)
        ctx = data_services.build_data_explorer_context(request, latest, model_name)
        result = ctx["result"]
        query_suffix = f"?{ctx['query_string']}" if ctx.get("query_string") else ""

        if not result.ok:
            json_text = viewer_utils.pretty_json(
                {"error": result.error, "records": []}
            )
            empty_msg = result.error or "Could not load live data."
        else:
            json_text = data_services.records_to_json(result.records)
            empty_msg = ""

        from django.urls import reverse

        viewer_ctx = viewer_utils.json_viewer_context(
            page_title=f"{model_name} · Data Explorer · JSON",
            title=f"Live records · {model_name}",
            subtitle=f"{instance.name} · audit #{latest.pk}",
            back_url=reverse(
                "data_explorer:model",
                kwargs={"instance_id": instance_id, "model_name": model_name},
            ),
            back_label="Back to Data Explorer",
            download_url=(
                reverse(
                    "data_explorer:export",
                    kwargs={
                        "instance_id": instance_id,
                        "model_name": model_name,
                        "format": "json",
                    },
                )
                + query_suffix
            ),
            json_text=json_text,
            source=f"Data Explorer · limit {ctx['limit']}",
            record_count=len(result.records) if result.ok else 0,
            empty_message=empty_msg,
            breadcrumbs=[
                {"label": "Dashboard", "url": reverse("instances:dashboard")},
                {
                    "label": "Data Explorer",
                    "url": reverse("data_explorer:index"),
                },
                {
                    "label": instance.name,
                    "url": reverse(
                        "data_explorer:instance", kwargs={"instance_id": instance_id}
                    ),
                },
                {
                    "label": model_name,
                    "url": reverse(
                        "data_explorer:model",
                        kwargs={
                            "instance_id": instance_id,
                            "model_name": model_name,
                        },
                    ),
                },
                {"label": "JSON", "url": ""},
            ],
        )
        from django.template.response import TemplateResponse

        return TemplateResponse(request, self.template_name, viewer_ctx)


class DataExplorerExportView(_ModelEntryMixin, View):
    """JSON / CSV export of the current Data Explorer slice."""

    def get(self, request, instance_id: int, model_name: str, format: str):
        if format not in data_services.DATA_EXPORT_FORMATS:
            raise Http404(f"Unsupported export format: {format!r}")

        _instance, latest = self._resolve(instance_id, model_name)
        ctx = data_services.build_data_explorer_context(request, latest, model_name)
        result = ctx["result"]

        if not result.ok:
            return HttpResponse(
                f"Could not fetch data: {result.error}\n",
                content_type="text/plain; charset=utf-8",
                status=502,
            )

        stem = data_services.export_filename_stem(latest, model_name)
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


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #

def _attachment(body: str, content_type: str, filename: str) -> HttpResponse:
    """Same shape as the audits app's helper, kept private to this module."""
    response = HttpResponse(body, content_type=f"{content_type}; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

"""In-browser JSON and Markdown report viewers (read-only, ownership-scoped)."""

from __future__ import annotations

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views import View

from . import data_services, explorer, viewer_utils
from .models import AuditRun
from .views import _ModelDataMixin, _OwnedAuditMixin


class ViewAuditJsonView(_OwnedAuditMixin, View):
    template_name = "audits/view_json.html"

    def get(self, request, pk: int):
        audit = get_object_or_404(self.get_queryset(), pk=pk)
        if not audit.json_report:
            ctx = viewer_utils.json_viewer_context(
                page_title=f"Audit #{audit.pk} · JSON",
                title="Full audit JSON",
                subtitle=_audit_subtitle(audit),
                back_url=audit.get_absolute_url(),
                download_url=reverse("audits:download_json", kwargs={"pk": pk}),
                json_text="",
                source="Full audit dataset",
                empty_message="This audit has no JSON dataset yet.",
                breadcrumbs=_audit_breadcrumbs(audit),
            )
            return TemplateResponse(request, self.template_name, ctx)

        ctx = viewer_utils.json_viewer_context(
            page_title=f"Audit #{audit.pk} · JSON",
            title="Full audit JSON",
            subtitle=_audit_subtitle(audit),
            back_url=audit.get_absolute_url(),
            download_url=reverse("audits:download_json", kwargs={"pk": pk}),
            json_text=viewer_utils.pretty_json(audit.json_report),
            source="Full audit dataset",
            breadcrumbs=_audit_breadcrumbs(audit),
        )
        return TemplateResponse(request, self.template_name, ctx)


class ViewAuditMarkdownView(_OwnedAuditMixin, View):
    template_name = "audits/view_markdown.html"

    def get(self, request, pk: int):
        audit = get_object_or_404(self.get_queryset(), pk=pk)
        ctx = viewer_utils.markdown_viewer_context(
            page_title=f"Audit #{audit.pk} · Markdown",
            title="Full audit Markdown report",
            subtitle=_audit_subtitle(audit),
            back_url=audit.get_absolute_url(),
            download_url=reverse("audits:download_markdown", kwargs={"pk": pk}),
            markdown_text=audit.markdown_report or "",
            source="Full audit report",
            empty_message="This audit has no Markdown report yet.",
            breadcrumbs=_audit_breadcrumbs(audit),
        )
        return TemplateResponse(request, self.template_name, ctx)


class ViewCategoryJsonView(_OwnedAuditMixin, View):
    template_name = "audits/view_json.html"

    def get(self, request, pk: int, category: str):
        cfg = explorer.get_category_config(category)
        if cfg is None:
            raise Http404(f"Unknown audit category: {category!r}")
        audit = get_object_or_404(self.get_queryset(), pk=pk)
        records = explorer.get_category_records(audit, category)
        ctx = viewer_utils.json_viewer_context(
            page_title=f"{cfg['title']} · Audit #{audit.pk} · JSON",
            title=f"{cfg['title']} records",
            subtitle=_audit_subtitle(audit),
            back_url=reverse("audits:explorer", kwargs={"pk": pk, "category": category}),
            back_label="Back to category",
            download_url=reverse(
                "audits:export_category",
                kwargs={"pk": pk, "category": category, "format": "json"},
            ),
            json_text=explorer.records_to_json(records),
            source=cfg["title"],
            record_count=len(records),
            breadcrumbs=_category_breadcrumbs(
                audit, category, cfg["title"], tail="JSON"
            ),
        )
        return TemplateResponse(request, self.template_name, ctx)


class ViewCategoryMarkdownView(_OwnedAuditMixin, View):
    template_name = "audits/view_markdown.html"

    def get(self, request, pk: int, category: str):
        cfg = explorer.get_category_config(category)
        if cfg is None:
            raise Http404(f"Unknown audit category: {category!r}")
        audit = get_object_or_404(self.get_queryset(), pk=pk)
        records = explorer.get_category_records(audit, category)
        body = explorer.records_to_markdown(audit, category, records)
        ctx = viewer_utils.markdown_viewer_context(
            page_title=f"{cfg['title']} · Audit #{audit.pk} · Markdown",
            title=f"{cfg['title']} report",
            subtitle=_audit_subtitle(audit),
            back_url=reverse("audits:explorer", kwargs={"pk": pk, "category": category}),
            back_label="Back to category",
            download_url=reverse(
                "audits:export_category",
                kwargs={"pk": pk, "category": category, "format": "md"},
            ),
            markdown_text=body,
            source=cfg["title"],
            record_count=len(records),
            breadcrumbs=_category_breadcrumbs(
                audit, category, cfg["title"], tail="Markdown"
            ),
        )
        return TemplateResponse(request, self.template_name, ctx)


class ViewModelJsonView(_OwnedAuditMixin, View):
    template_name = "audits/view_json.html"

    def get(self, request, pk: int, model_name: str):
        audit = get_object_or_404(self.get_queryset(), pk=pk)
        payload = explorer.build_model_detail_payload(audit, model_name)
        if payload is None:
            raise Http404(f"Model {model_name!r} not in audit.")
        ctx = viewer_utils.json_viewer_context(
            page_title=f"{model_name} · Audit #{audit.pk} · JSON",
            title=f"Model profile · {model_name}",
            subtitle=_audit_subtitle(audit),
            back_url=reverse(
                "audits:model_detail",
                kwargs={"pk": pk, "model_name": model_name},
            ),
            back_label="Back to model",
            download_url=reverse(
                "audits:export_model_detail",
                kwargs={"pk": pk, "model_name": model_name, "format": "json"},
            ),
            json_text=explorer.model_detail_to_json(payload),
            source=model_name,
            breadcrumbs=_model_breadcrumbs(audit, model_name),
        )
        return TemplateResponse(request, self.template_name, ctx)


class ViewModelMarkdownView(_OwnedAuditMixin, View):
    template_name = "audits/view_markdown.html"

    def get(self, request, pk: int, model_name: str):
        audit = get_object_or_404(self.get_queryset(), pk=pk)
        payload = explorer.build_model_detail_payload(audit, model_name)
        if payload is None:
            raise Http404(f"Model {model_name!r} not in audit.")
        body = explorer.model_detail_to_markdown(audit, model_name, payload)
        ctx = viewer_utils.markdown_viewer_context(
            page_title=f"{model_name} · Audit #{audit.pk} · Markdown",
            title=f"Model report · {model_name}",
            subtitle=_audit_subtitle(audit),
            back_url=reverse(
                "audits:model_detail",
                kwargs={"pk": pk, "model_name": model_name},
            ),
            back_label="Back to model",
            download_url=reverse(
                "audits:export_model_detail",
                kwargs={"pk": pk, "model_name": model_name, "format": "md"},
            ),
            markdown_text=body,
            source=model_name,
            breadcrumbs=_model_markdown_breadcrumbs(audit, model_name),
        )
        return TemplateResponse(request, self.template_name, ctx)


class ViewModelDataJsonView(_ModelDataMixin, View):
    """Pretty JSON view of the current Model Data Explorer slice."""

    template_name = "audits/view_json.html"

    def get(self, request, pk: int, model_name: str):
        ctx_data = self._load(request, pk, model_name)
        audit = ctx_data["audit"]
        result = ctx_data["result"]
        query_suffix = f"?{ctx_data['query_string']}" if ctx_data.get("query_string") else ""

        if not result.ok:
            json_text = viewer_utils.pretty_json(
                {"error": result.error, "records": []}
            )
            empty_msg = result.error or "Could not load live data."
        else:
            json_text = data_services.records_to_json(result.records)
            empty_msg = ""

        viewer_ctx = viewer_utils.json_viewer_context(
            page_title=f"{model_name} · Live data · JSON",
            title=f"Live records · {model_name}",
            subtitle=_audit_subtitle(audit),
            back_url=reverse(
                "audits:model_data_explorer",
                kwargs={"pk": pk, "model_name": model_name},
            ),
            back_label="Back to data explorer",
            download_url=(
                reverse(
                    "audits:export_model_data",
                    kwargs={"pk": pk, "model_name": model_name, "format": "json"},
                )
                + query_suffix
            ),
            json_text=json_text,
            source=f"Live Odoo data · limit {ctx_data['limit']}",
            record_count=len(result.records) if result.ok else 0,
            empty_message=empty_msg,
            breadcrumbs=_model_data_breadcrumbs(audit, model_name),
        )
        return TemplateResponse(request, self.template_name, viewer_ctx)


def _audit_subtitle(audit: AuditRun) -> str:
    when = audit.finished_at or audit.created_at
    when_label = when.strftime("%b %d, %Y %H:%M") if when else "—"
    return f"{audit.instance.name} · generated {when_label}"


def _audit_breadcrumbs(audit: AuditRun) -> list[dict[str, str]]:
    return [
        {"label": "Dashboard", "url": reverse("instances:dashboard")},
        {
            "label": audit.instance.name,
            "url": audit.instance.get_absolute_url(),
        },
        {"label": f"Audit #{audit.pk}", "url": audit.get_absolute_url()},
        {"label": "JSON", "url": ""},
    ]


def _category_breadcrumbs(
    audit: AuditRun, category: str, title: str, *, tail: str = "JSON"
) -> list[dict[str, str]]:
    crumbs = _audit_breadcrumbs(audit)[:-1]
    crumbs.append(
        {
            "label": title,
            "url": reverse(
                "audits:explorer", kwargs={"pk": audit.pk, "category": category}
            ),
        }
    )
    crumbs.append({"label": tail, "url": ""})
    return crumbs


def _model_breadcrumbs(audit: AuditRun, model_name: str) -> list[dict[str, str]]:
    crumbs = _audit_breadcrumbs(audit)[:-1]
    crumbs.append(
        {
            "label": "Models",
            "url": reverse("audits:explorer", kwargs={"pk": audit.pk, "category": "models"}),
        }
    )
    crumbs.append(
        {
            "label": model_name,
            "url": reverse(
                "audits:model_detail",
                kwargs={"pk": audit.pk, "model_name": model_name},
            ),
        }
    )
    crumbs.append({"label": "JSON", "url": ""})
    return crumbs


def _model_markdown_breadcrumbs(audit: AuditRun, model_name: str) -> list[dict[str, str]]:
    crumbs = _model_breadcrumbs(audit, model_name)
    crumbs[-1] = {"label": "Markdown", "url": ""}
    return crumbs


def _model_data_breadcrumbs(audit: AuditRun, model_name: str) -> list[dict[str, str]]:
    crumbs = _model_breadcrumbs(audit, model_name)[:-1]
    crumbs.append(
        {
            "label": "Live data",
            "url": reverse(
                "audits:model_data_explorer",
                kwargs={"pk": audit.pk, "model_name": model_name},
            ),
        }
    )
    crumbs.append({"label": "JSON", "url": ""})
    return crumbs

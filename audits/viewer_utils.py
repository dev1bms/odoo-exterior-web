"""Shared helpers for in-browser JSON and Markdown report viewers."""

from __future__ import annotations

import json
import re
from typing import Any

from django.utils.html import escape
from django.utils.safestring import mark_safe


_UNSAFE_TAG_RE = re.compile(
    r"<\s*/?\s*(script|style|iframe|object|embed|form|input|meta|link)\b[^>]*>",
    re.IGNORECASE,
)
_EVENT_ATTR_RE = re.compile(r"\s+on\w+\s*=\s*[^>]*", re.IGNORECASE)
_JAVASCRIPT_HREF_RE = re.compile(r"href\s*=\s*['\"]?\s*javascript:", re.IGNORECASE)


def pretty_json(data: Any) -> str:
    """Serialize *data* as indented JSON for display in a ``<pre>`` block."""
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def sanitize_html(html: str) -> str:
    """Strip obviously dangerous markup from rendered Markdown HTML."""
    cleaned = _UNSAFE_TAG_RE.sub("", html)
    cleaned = _EVENT_ATTR_RE.sub("", cleaned)
    cleaned = _JAVASCRIPT_HREF_RE.sub('href="#"', cleaned)
    return cleaned


def render_markdown(text: str) -> tuple[str, bool]:
    """Return ``(content, rendered_as_html)`` for the Markdown viewer.

    When the optional ``markdown`` package is unavailable, falls back to
    escaped plain text inside a ``<pre>`` (caller wraps accordingly).
    """
    if not text:
        return "", False
    try:
        import markdown as md  # type: ignore[import-not-found]
    except ImportError:
        return escape(text), False

    raw_html = md.markdown(
        text,
        extensions=["fenced_code", "tables", "sane_lists", "nl2br"],
        output_format="html5",
    )
    safe = sanitize_html(raw_html)
    return mark_safe(safe), True  # noqa: S703 — sanitized above


def json_viewer_context(
    *,
    page_title: str,
    title: str,
    subtitle: str = "",
    back_url: str,
    back_label: str = "Back",
    download_url: str,
    download_label: str = "Download JSON",
    json_text: str,
    source: str = "",
    record_count: int | None = None,
    empty_message: str = "",
    breadcrumbs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build template context for :template:`audits/view_json.html`."""
    return {
        "page_title": page_title,
        "viewer_title": title,
        "viewer_subtitle": subtitle,
        "back_url": back_url,
        "back_label": back_label,
        "download_url": download_url,
        "download_label": download_label,
        "json_text": json_text,
        "viewer_source": source,
        "record_count": record_count,
        "empty_message": empty_message,
        "has_content": bool(json_text.strip()),
        "breadcrumbs": breadcrumbs or [],
        "format_label": "JSON",
        "copy_target_id": "viewer-content",
    }


def markdown_viewer_context(
    *,
    page_title: str,
    title: str,
    subtitle: str = "",
    back_url: str,
    back_label: str = "Back",
    download_url: str,
    download_label: str = "Download Markdown",
    markdown_text: str,
    source: str = "",
    record_count: int | None = None,
    empty_message: str = "",
    breadcrumbs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build template context for :template:`audits/view_markdown.html`."""
    content, rendered_as_html = render_markdown(markdown_text) if markdown_text else ("", False)
    copy_target_id = "viewer-content-raw" if rendered_as_html else "viewer-content"
    return {
        "page_title": page_title,
        "viewer_title": title,
        "viewer_subtitle": subtitle,
        "back_url": back_url,
        "back_label": back_label,
        "download_url": download_url,
        "download_label": download_label,
        "markdown_text": markdown_text,
        "markdown_content": content,
        "markdown_rendered_as_html": rendered_as_html,
        "viewer_source": source,
        "record_count": record_count,
        "empty_message": empty_message or "No Markdown content is available for this report.",
        "has_content": bool(markdown_text.strip()),
        "breadcrumbs": breadcrumbs or [],
        "format_label": "Markdown",
        "copy_target_id": copy_target_id,
    }

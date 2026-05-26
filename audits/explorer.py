"""Audit Explorer: per-category configuration, rendering, and export helpers.

Single source of truth for:

* the categories shown on the audit detail page (as clickable cards),
* the columns rendered on the explorer page for each category,
* the JSON / CSV / Markdown serializers used by the export endpoint.

The functions here are pure (no Django request/response): views and templates
consume what these helpers return.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Iterable

# --------------------------------------------------------------------- #
# Public constants
# --------------------------------------------------------------------- #

#: Categories the explorer knows how to render.
#:
#: Each entry maps ``slug -> {title, icon, description, json_key, columns}``.
#: ``json_key`` is the key in ``AuditRun.json_report`` where the list of
#: records lives.
#: ``columns`` is an ordered list of ``{key, label, kind}`` dicts. ``kind``
#: hints the renderer how to display the value (``bool``, ``m2o``,
#: ``badge``, ``code``, ``preview``, ``list`` or ``None`` for plain text).
CATEGORY_CONFIG: dict[str, dict[str, Any]] = {
    "models": {
        "title": "Models",
        "icon": "bi-database",
        "description": "Custom Studio models and standard models with Studio fields.",
        "json_key": "models",
        "columns": [
            {"key": "model", "label": "Technical name", "kind": "code"},
            {"key": "name", "label": "Display name"},
            {"key": "state", "label": "State", "kind": "badge"},
            {"key": "transient", "label": "Transient", "kind": "bool"},
            {"key": "modules", "label": "Modules"},
        ],
    },
    "fields": {
        "title": "Fields",
        "icon": "bi-input-cursor-text",
        "description": "Studio fields detected across models.",
        "json_key": "fields",
        "columns": [
            {"key": "model", "label": "Model", "kind": "code"},
            {"key": "name", "label": "Name", "kind": "code"},
            {"key": "field_description", "label": "Label"},
            {"key": "ttype", "label": "Type", "kind": "badge"},
            {"key": "relation", "label": "Relation", "kind": "code"},
            {"key": "required", "label": "Required", "kind": "bool"},
            {"key": "readonly", "label": "Readonly", "kind": "bool"},
            {"key": "store", "label": "Stored", "kind": "bool"},
            {"key": "state", "label": "State", "kind": "badge"},
        ],
    },
    "views": {
        "title": "Views",
        "icon": "bi-window-stack",
        "description": "Modified and Studio-generated views.",
        "json_key": "views",
        "columns": [
            {"key": "name", "label": "Name"},
            {"key": "model", "label": "Model", "kind": "code"},
            {"key": "type", "label": "Type", "kind": "badge"},
            {"key": "inherit_id", "label": "Inherits from", "kind": "m2o"},
            {"key": "priority", "label": "Priority"},
            {"key": "active", "label": "Active", "kind": "bool"},
        ],
    },
    "server_actions": {
        "title": "Server Actions",
        "icon": "bi-lightning-charge",
        "description": "Server-side actions linked to custom models.",
        "json_key": "server_actions",
        "columns": [
            {"key": "name", "label": "Name"},
            {"key": "model_name", "label": "Model", "kind": "code"},
            {"key": "state", "label": "State", "kind": "badge"},
            {"key": "usage", "label": "Usage", "kind": "badge"},
            {"key": "code", "label": "Code preview", "kind": "preview"},
        ],
    },
    "automations": {
        "title": "Automations",
        "icon": "bi-arrow-repeat",
        "description": "base.automation rules tied to custom models.",
        "json_key": "automations",
        "columns": [
            {"key": "name", "label": "Name"},
            {"key": "model_name", "label": "Model", "kind": "code"},
            {"key": "trigger", "label": "Trigger", "kind": "badge"},
            {"key": "active", "label": "Active", "kind": "bool"},
        ],
    },
    "menus": {
        "title": "Menus",
        "icon": "bi-list-ul",
        "description": "Menu entries that point at the audited custom actions.",
        "json_key": "menus",
        "columns": [
            {"key": "complete_name", "label": "Name"},
            {"key": "parent_id", "label": "Parent", "kind": "m2o"},
            {"key": "action", "label": "Action", "kind": "code"},
            {"key": "sequence", "label": "Sequence"},
            {"key": "active", "label": "Active", "kind": "bool"},
        ],
    },
    "window_actions": {
        "title": "Window Actions",
        "icon": "bi-window",
        "description": "ir.actions.act_window entries for custom models.",
        "json_key": "window_actions",
        "columns": [
            {"key": "name", "label": "Name"},
            {"key": "res_model", "label": "Model", "kind": "code"},
            {"key": "view_mode", "label": "View mode", "kind": "code"},
            {"key": "target", "label": "Target", "kind": "badge"},
        ],
    },
    "access_rights": {
        "title": "Access Rights",
        "icon": "bi-shield-lock",
        "description": "ir.model.access entries for custom models.",
        "json_key": "access_rights",
        "columns": [
            {"key": "name", "label": "Name"},
            {"key": "model_id", "label": "Model", "kind": "m2o"},
            {"key": "group_id", "label": "Group", "kind": "m2o"},
            {"key": "perm_read", "label": "Read", "kind": "bool"},
            {"key": "perm_write", "label": "Write", "kind": "bool"},
            {"key": "perm_create", "label": "Create", "kind": "bool"},
            {"key": "perm_unlink", "label": "Unlink", "kind": "bool"},
        ],
    },
    "record_rules": {
        "title": "Record Rules",
        "icon": "bi-shield-shaded",
        "description": "ir.rule entries for custom models.",
        "json_key": "record_rules",
        "columns": [
            {"key": "name", "label": "Name"},
            {"key": "model_id", "label": "Model", "kind": "m2o"},
            {"key": "groups", "label": "Groups", "kind": "list"},
            {"key": "domain_force", "label": "Domain", "kind": "preview"},
            {"key": "active", "label": "Active", "kind": "bool"},
        ],
    },
}


#: Export formats accepted by the export endpoint.
EXPORT_FORMATS: tuple[str, ...] = ("json", "md", "csv")


# --------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------- #

def get_category_config(category: str) -> dict[str, Any] | None:
    """Return the config for ``category`` or ``None`` if unknown."""
    return CATEGORY_CONFIG.get(category)


def get_category_columns(category: str) -> list[dict[str, Any]]:
    """Return the column definitions for ``category`` (or an empty list)."""
    cfg = CATEGORY_CONFIG.get(category)
    return list(cfg["columns"]) if cfg else []


def get_category_records(audit, category: str) -> list[dict[str, Any]]:
    """Return the list of records for ``category`` from ``audit.json_report``.

    Returns an empty list if the audit has no JSON report or the category
    key is missing.
    """
    cfg = CATEGORY_CONFIG.get(category)
    if not cfg:
        return []
    payload = audit.json_report or {}
    raw = payload.get(cfg["json_key"], [])
    return list(raw) if isinstance(raw, list) else []


def build_category_cards(audit) -> list[dict[str, Any]]:
    """Build the list of clickable metric cards shown on the detail page.

    Each card contains: ``slug``, ``title``, ``icon``, ``description``, and
    ``count`` (from ``audit.summary`` when present, else from the JSON list
    length, else 0).
    """
    summary = audit.summary or {}
    payload = audit.json_report or {}
    cards: list[dict[str, Any]] = []
    for slug, cfg in CATEGORY_CONFIG.items():
        key = cfg["json_key"]
        if key in summary:
            count = summary.get(key) or 0
        else:
            raw = payload.get(key)
            count = len(raw) if isinstance(raw, list) else 0
        cards.append(
            {
                "slug": slug,
                "title": cfg["title"],
                "icon": cfg["icon"],
                "description": cfg["description"],
                "count": count,
            }
        )
    return cards


# --------------------------------------------------------------------- #
# Value formatting
# --------------------------------------------------------------------- #

_DEFAULT_CELL_LIMIT = 80
_PREVIEW_CELL_LIMIT = 120


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _is_m2o_tuple(value: Any) -> bool:
    """Detect Odoo many2one wire format ``[id, "display name"]``."""
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], int)
        and isinstance(value[1], str)
    )


def format_cell_value(value: Any, kind: str | None = None) -> str:
    """Return a flat string suitable for CSV/Markdown serialization.

    * ``None`` and Odoo's "missing" ``False`` for m2o/text fields become
      empty strings (unless ``kind == 'bool'``).
    * Odoo many2one tuples ``[id, name]`` collapse to the display name.
    * Lists / dicts that don't look like an m2o get serialized as JSON.
    """
    if kind == "bool":
        return "true" if bool(value) else "false"

    if value is None:
        return ""
    if value is False and kind != "bool":
        # Odoo serializes "no value" as False for many fields.
        return ""

    if _is_m2o_tuple(value):
        return str(value[1])

    if isinstance(value, (list, tuple)):
        parts: list[str] = []
        for item in value:
            if _is_m2o_tuple(item):
                parts.append(str(item[1]))
            else:
                parts.append(format_cell_value(item))
        return ", ".join(p for p in parts if p)

    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)

    return str(value)


def render_cell(record: dict[str, Any], column: dict[str, Any]) -> dict[str, Any]:
    """Pre-render one cell for the explorer template.

    Returns a dict the template can consume directly:

    * ``display`` — the (possibly truncated) text to show in the cell
    * ``title``  — the full untruncated text (for the ``title`` attribute)
    * ``kind``   — column kind, used by the template to pick a style
    * ``bool``   — ``True``/``False``/``None``; ``None`` means "not a bool"
    * ``empty``  — ``True`` if there is no value to render
    """
    raw = record.get(column["key"]) if record else None
    kind = column.get("kind")

    # Booleans are rendered as a coloured pill in the template.
    if kind == "bool":
        b = bool(raw)
        return {
            "display": "true" if b else "false",
            "title": "true" if b else "false",
            "kind": "bool",
            "bool": b,
            "empty": False,
        }

    flat = format_cell_value(raw, kind)
    if flat == "":
        return {
            "display": "",
            "title": "",
            "kind": "empty",
            "bool": None,
            "empty": True,
        }

    limit = _PREVIEW_CELL_LIMIT if kind == "preview" else _DEFAULT_CELL_LIMIT
    display = _truncate(flat, limit)
    return {
        "display": display,
        "title": flat,
        "kind": kind or "text",
        "bool": None,
        "empty": False,
    }


def build_rows(
    records: Iterable[dict[str, Any]],
    columns: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Pre-render every record into a 2D list of cell dicts for the template."""
    rendered: list[list[dict[str, Any]]] = []
    for record in records:
        rendered.append([render_cell(record, col) for col in columns])
    return rendered


# --------------------------------------------------------------------- #
# Serializers used by the export endpoint
# --------------------------------------------------------------------- #

def records_to_json(records: Iterable[dict[str, Any]]) -> str:
    """Return the records list as pretty-printed JSON text."""
    return json.dumps(list(records), indent=2, ensure_ascii=False, default=str)


def records_to_csv(
    records: Iterable[dict[str, Any]],
    columns: list[dict[str, Any]],
) -> str:
    """Return a CSV document with the configured columns as headers."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([col["label"] for col in columns])
    for record in records:
        writer.writerow(
            [format_cell_value(record.get(col["key"]), col.get("kind")) for col in columns]
        )
    return buffer.getvalue()


def _md_escape(text: str) -> str:
    """Escape pipes and newlines so a value fits inside one Markdown cell."""
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def records_to_markdown(
    audit,
    category: str,
    records: Iterable[dict[str, Any]],
) -> str:
    """Return a Markdown document for one category of one audit."""
    cfg = CATEGORY_CONFIG.get(category)
    if not cfg:
        return f"# Unknown category: {category}\n"
    columns = cfg["columns"]
    records = list(records)

    lines: list[str] = []
    instance_name = getattr(getattr(audit, "instance", None), "name", "")
    lines.append(f"# Odoo Exterior — {cfg['title']}")
    lines.append("")
    lines.append(f"- **Audit:** #{audit.pk}")
    if instance_name:
        lines.append(f"- **Instance:** {instance_name}")
    lines.append(f"- **Category:** `{category}`")
    lines.append(f"- **Count:** {len(records)}")
    lines.append("")

    if not records:
        lines.append("_No records in this category._")
        lines.append("")
        return "\n".join(lines)

    # Header row
    lines.append("| " + " | ".join(col["label"] for col in columns) + " |")
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for record in records:
        cells = [
            _md_escape(format_cell_value(record.get(col["key"]), col.get("kind")))
            for col in columns
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)

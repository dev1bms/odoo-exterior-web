"""Audit Explorer: per-category configuration, rendering, and export helpers.

Single source of truth for:

* the categories shown on the audit detail page (as clickable cards),
* the columns rendered on the explorer page for each category,
* the JSON / CSV / Markdown serializers used by the export endpoint,
* the per-model drill-down payload (see ``build_model_detail_payload``).

The functions here are pure (no Django request/response): views and templates
consume what these helpers return.
"""

from __future__ import annotations

import csv
import io
import json
import re
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

    _emit_markdown_table(lines, columns, records)
    lines.append("")
    return "\n".join(lines)


def _emit_markdown_table(
    lines: list[str],
    columns: list[dict[str, Any]],
    records: Iterable[dict[str, Any]],
) -> None:
    """Append a GitHub-Flavored-Markdown table to ``lines`` in place."""
    lines.append("| " + " | ".join(col["label"] for col in columns) + " |")
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for record in records:
        cells = [
            _md_escape(format_cell_value(record.get(col["key"]), col.get("kind")))
            for col in columns
        ]
        lines.append("| " + " | ".join(cells) + " |")


# --------------------------------------------------------------------- #
# Model drill-down: column sets
# --------------------------------------------------------------------- #
#
# The model-detail page already knows which model the user is looking at,
# so each table omits its "model" / "model_name" / "res_model" column to
# avoid redundant noise. Otherwise these column sets mirror the columns
# used by the corresponding category in CATEGORY_CONFIG.

MODEL_FIELDS_COLUMNS: list[dict[str, Any]] = [
    {"key": "name", "label": "Name", "kind": "code"},
    {"key": "field_description", "label": "Label"},
    {"key": "ttype", "label": "Type", "kind": "badge"},
    {"key": "relation", "label": "Relation", "kind": "code"},
    {"key": "required", "label": "Required", "kind": "bool"},
    {"key": "readonly", "label": "Readonly", "kind": "bool"},
    {"key": "store", "label": "Stored", "kind": "bool"},
    {"key": "state", "label": "State", "kind": "badge"},
]

MODEL_VIEWS_COLUMNS: list[dict[str, Any]] = [
    {"key": "name", "label": "Name"},
    {"key": "type", "label": "Type", "kind": "badge"},
    {"key": "inherit_id", "label": "Inherits from", "kind": "m2o"},
    {"key": "priority", "label": "Priority"},
    {"key": "active", "label": "Active", "kind": "bool"},
    {"key": "arch_db", "label": "Arch preview", "kind": "preview"},
]

MODEL_SERVER_ACTIONS_COLUMNS: list[dict[str, Any]] = [
    {"key": "name", "label": "Name"},
    {"key": "state", "label": "State", "kind": "badge"},
    {"key": "usage", "label": "Usage", "kind": "badge"},
    {"key": "type", "label": "Type", "kind": "badge"},
    {"key": "code", "label": "Code preview", "kind": "preview"},
]

MODEL_WINDOW_ACTIONS_COLUMNS: list[dict[str, Any]] = [
    {"key": "name", "label": "Name"},
    {"key": "view_mode", "label": "View mode", "kind": "code"},
    {"key": "target", "label": "Target", "kind": "badge"},
    {"key": "_menu_name", "label": "Menu", "kind": "code"},
]

MODEL_MENUS_COLUMNS: list[dict[str, Any]] = [
    {"key": "complete_name", "label": "Menu"},
    {"key": "parent_id", "label": "Parent", "kind": "m2o"},
    {"key": "action", "label": "Action", "kind": "code"},
    {"key": "sequence", "label": "Sequence"},
    {"key": "active", "label": "Active", "kind": "bool"},
]

MODEL_ACCESS_COLUMNS: list[dict[str, Any]] = [
    {"key": "name", "label": "Name"},
    {"key": "group_id", "label": "Group", "kind": "m2o"},
    {"key": "perm_read", "label": "Read", "kind": "bool"},
    {"key": "perm_write", "label": "Write", "kind": "bool"},
    {"key": "perm_create", "label": "Create", "kind": "bool"},
    {"key": "perm_unlink", "label": "Unlink", "kind": "bool"},
]

MODEL_RULES_COLUMNS: list[dict[str, Any]] = [
    {"key": "name", "label": "Name"},
    {"key": "groups", "label": "Groups", "kind": "list"},
    {"key": "domain_force", "label": "Domain", "kind": "preview"},
    {"key": "active", "label": "Active", "kind": "bool"},
]

MODEL_OUTGOING_REL_COLUMNS: list[dict[str, Any]] = [
    {"key": "name", "label": "Field", "kind": "code"},
    {"key": "field_description", "label": "Label"},
    {"key": "ttype", "label": "Type", "kind": "badge"},
    {"key": "relation", "label": "Relation", "kind": "code"},
]

MODEL_INCOMING_REL_COLUMNS: list[dict[str, Any]] = [
    {"key": "model", "label": "Source model", "kind": "code"},
    {"key": "name", "label": "Field", "kind": "code"},
    {"key": "field_description", "label": "Label"},
    {"key": "ttype", "label": "Type", "kind": "badge"},
]

#: Sections rendered on the model detail page, in display order.
#: Each entry: ``(slug, title, icon, payload_key, columns)``.
MODEL_DETAIL_SECTIONS: tuple[tuple[str, str, str, str, list[dict[str, Any]]], ...] = (
    ("fields",          "Fields",          "bi-input-cursor-text", "fields",          MODEL_FIELDS_COLUMNS),
    ("views",           "Views",           "bi-window-stack",      "views",           MODEL_VIEWS_COLUMNS),
    ("server_actions",  "Server Actions",  "bi-lightning-charge",  "server_actions",  MODEL_SERVER_ACTIONS_COLUMNS),
    ("window_actions",  "Window Actions",  "bi-window",            "window_actions",  MODEL_WINDOW_ACTIONS_COLUMNS),
    ("menus",           "Menus",           "bi-list-ul",           "menus",           MODEL_MENUS_COLUMNS),
    ("access_rights",   "Access Rights",   "bi-shield-lock",       "access_rights",   MODEL_ACCESS_COLUMNS),
    ("record_rules",    "Record Rules",    "bi-shield-shaded",     "record_rules",    MODEL_RULES_COLUMNS),
)

#: Export formats accepted by the model-detail export endpoint.
MODEL_EXPORT_FORMATS: tuple[str, ...] = ("json", "md")

#: Candidate keys that may carry a model reference, by category.
#: Used by the defensive matcher to find records referencing a model.
_MODEL_REF_KEYS: dict[str, tuple[str, ...]] = {
    "fields":         ("model",),
    "views":          ("model",),
    "server_actions": ("model_name", "model", "model_id", "crud_model_id", "binding_model_id"),
    "automations":    ("model_name", "model", "model_id"),
    "window_actions": ("res_model", "binding_model_id"),
    "access_rights":  ("model_name", "model", "model_id"),
    "record_rules":   ("model_name", "model", "model_id"),
}


# --------------------------------------------------------------------- #
# Model drill-down: helpers
# --------------------------------------------------------------------- #

def get_model_identifier(record: dict[str, Any] | None) -> str | None:
    """Return the technical name of a model record (defensive over key names).

    Tries, in order: ``model``, ``technical_name``, ``name``. Returns the
    first non-empty string match or ``None``.
    """
    if not isinstance(record, dict):
        return None
    for key in ("model", "technical_name", "name"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _build_model_id_index(audit) -> dict[int, str]:
    """Map ``ir.model`` id -> technical name from the audit's models list.

    Used to resolve many2one references like ``[80, "Dashboard"]`` (where
    the display name is the human label, not the technical name) back to
    the technical model name.
    """
    payload = getattr(audit, "json_report", None) or {}
    index: dict[int, str] = {}
    for record in payload.get("models", []) or []:
        if not isinstance(record, dict):
            continue
        mid = record.get("id")
        tname = get_model_identifier(record)
        if isinstance(mid, int) and tname:
            index[mid] = tname
    return index


def model_name_matches(value: Any, model_name: str) -> bool:
    """Return ``True`` if ``value`` references ``model_name``.

    Accepts strings (compared directly), Odoo m2o tuples ``[id, name]``
    (the display name segment is compared), and lists of any of the above
    (matches if any element matches). ``None`` and ``False`` never match.

    Note: when the m2o display name is the *label* and not the technical
    name, prefer :func:`_value_references_model` which also resolves via
    the audit's model-id index.
    """
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value == model_name
    if _is_m2o_tuple(value):
        return str(value[1]) == model_name
    if isinstance(value, (list, tuple)):
        return any(model_name_matches(item, model_name) for item in value)
    return False


def _value_references_model(
    value: Any,
    model_name: str,
    id_to_name: dict[int, str],
) -> bool:
    """Like :func:`model_name_matches` but resolves m2o ids via ``id_to_name``."""
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value == model_name
    if _is_m2o_tuple(value):
        tname = id_to_name.get(value[0])
        if tname is not None:
            return tname == model_name
        return str(value[1]) == model_name
    if isinstance(value, (list, tuple)):
        return any(_value_references_model(item, model_name, id_to_name) for item in value)
    return False


def _record_references_model(
    record: dict[str, Any],
    model_name: str,
    keys: Iterable[str],
    id_to_name: dict[int, str],
) -> bool:
    """Defensive match: does any of ``record[k]`` reference ``model_name``?"""
    if not isinstance(record, dict):
        return False
    for key in keys:
        if key in record and _value_references_model(record.get(key), model_name, id_to_name):
            return True
    return False


def _filter_by_model(
    audit,
    category: str,
    model_name: str,
    id_to_name: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Return records from ``audit.json_report[category]`` referencing ``model_name``."""
    if id_to_name is None:
        id_to_name = _build_model_id_index(audit)
    keys = _MODEL_REF_KEYS.get(category, ())
    payload = getattr(audit, "json_report", None) or {}
    return [
        rec for rec in payload.get(category, []) or []
        if isinstance(rec, dict)
        and _record_references_model(rec, model_name, keys, id_to_name)
    ]


# Per-category public accessors -------------------------------------------- #

def get_model_record(audit, model_name: str) -> dict[str, Any] | None:
    """Return the ``ir.model`` row for ``model_name`` (or ``None``)."""
    payload = getattr(audit, "json_report", None) or {}
    for rec in payload.get("models", []) or []:
        if isinstance(rec, dict) and get_model_identifier(rec) == model_name:
            return rec
    return None


def get_model_fields(audit, model_name: str) -> list[dict[str, Any]]:
    return _filter_by_model(audit, "fields", model_name)


def get_model_views(audit, model_name: str) -> list[dict[str, Any]]:
    return _filter_by_model(audit, "views", model_name)


def get_model_server_actions(audit, model_name: str) -> list[dict[str, Any]]:
    return _filter_by_model(audit, "server_actions", model_name)


def get_model_window_actions(audit, model_name: str) -> list[dict[str, Any]]:
    return _filter_by_model(audit, "window_actions", model_name)


_ACT_WINDOW_RE = re.compile(r"^\s*ir\.actions\.act_window\s*,\s*(\d+)\s*$")


def _window_action_ids_for_model(audit, model_name: str) -> set[int]:
    return {
        rec.get("id")
        for rec in get_model_window_actions(audit, model_name)
        if isinstance(rec.get("id"), int)
    }


def get_model_menus(audit, model_name: str) -> list[dict[str, Any]]:
    """Return menus whose ``act_window`` action targets ``model_name``.

    Strategy:
      1. Collect window-action ids for this model.
      2. Scan menus whose ``action`` field is the canonical Odoo
         ``"ir.actions.act_window,<id>"`` string and whose id is in (1).

    This deliberately does *not* try to guess for menus whose action
    reference cannot be parsed reliably from the JSON.
    """
    wa_ids = _window_action_ids_for_model(audit, model_name)
    if not wa_ids:
        return []
    payload = getattr(audit, "json_report", None) or {}
    out: list[dict[str, Any]] = []
    for rec in payload.get("menus", []) or []:
        if not isinstance(rec, dict):
            continue
        action = rec.get("action")
        if not isinstance(action, str):
            continue
        m = _ACT_WINDOW_RE.match(action)
        if m and int(m.group(1)) in wa_ids:
            out.append(rec)
    return out


def get_model_access_rights(audit, model_name: str) -> list[dict[str, Any]]:
    return _filter_by_model(audit, "access_rights", model_name)


def get_model_record_rules(audit, model_name: str) -> list[dict[str, Any]]:
    return _filter_by_model(audit, "record_rules", model_name)


def get_model_relationships(
    audit,
    model_name: str,
) -> dict[str, list[dict[str, Any]]]:
    """Return ``{"outgoing": [...], "incoming": [...]}`` for ``model_name``.

    * ``outgoing`` — fields on this model that have a non-empty ``relation``.
    * ``incoming`` — fields on *other* models that point at this model.
    """
    payload = getattr(audit, "json_report", None) or {}
    all_fields = [f for f in payload.get("fields", []) or [] if isinstance(f, dict)]

    outgoing = [
        f for f in all_fields
        if f.get("model") == model_name
        and isinstance(f.get("relation"), str)
        and f.get("relation")
    ]
    incoming = [
        f for f in all_fields
        if f.get("relation") == model_name
        and f.get("model") != model_name
    ]
    return {"outgoing": outgoing, "incoming": incoming}


# --------------------------------------------------------------------- #
# Model drill-down: payload + serializers
# --------------------------------------------------------------------- #

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_model_filename(model_name: str) -> str:
    """Return a filesystem-safe version of a model name (e.g. for downloads)."""
    cleaned = _FILENAME_SAFE_RE.sub("_", model_name).strip("._-")
    return cleaned or "model"


def build_model_detail_payload(audit, model_name: str) -> dict[str, Any] | None:
    """Aggregate every section of a model's drill-down profile.

    Returns ``None`` when the model is not present in ``audit.json_report``,
    which the view turns into a 404. The returned dict is what the template
    and exporters consume.
    """
    model_record = get_model_record(audit, model_name)
    if model_record is None:
        return None

    fields = get_model_fields(audit, model_name)
    views = get_model_views(audit, model_name)
    server_actions = get_model_server_actions(audit, model_name)
    window_actions = get_model_window_actions(audit, model_name)
    menus = get_model_menus(audit, model_name)
    access_rights = get_model_access_rights(audit, model_name)
    record_rules = get_model_record_rules(audit, model_name)
    relationships = get_model_relationships(audit, model_name)

    # Annotate each window action with the menu (if any) that surfaces it.
    wa_id_to_menu: dict[int, str] = {}
    for menu in menus:
        action = menu.get("action") if isinstance(menu, dict) else None
        if isinstance(action, str):
            m = _ACT_WINDOW_RE.match(action)
            if m:
                label = menu.get("complete_name") or menu.get("name") or ""
                wa_id_to_menu[int(m.group(1))] = str(label)
    annotated_window_actions = [
        {**wa, "_menu_name": wa_id_to_menu.get(wa.get("id"), "")}
        for wa in window_actions
    ]

    summary = {
        "fields": len(fields),
        "views": len(views),
        "server_actions": len(server_actions),
        "window_actions": len(window_actions),
        "menus": len(menus),
        "access_rights": len(access_rights),
        "record_rules": len(record_rules),
        "outgoing_relations": len(relationships["outgoing"]),
        "incoming_relations": len(relationships["incoming"]),
    }

    return {
        "audit_id": audit.pk,
        "instance_name": getattr(getattr(audit, "instance", None), "name", ""),
        "model_name": model_name,
        "model_record": model_record,
        "fields": fields,
        "views": views,
        "server_actions": server_actions,
        "window_actions": annotated_window_actions,
        "menus": menus,
        "access_rights": access_rights,
        "record_rules": record_rules,
        "relationships": relationships,
        "summary": summary,
    }


#: Cards rendered as the summary metric strip on the model detail page.
#: Each entry: ``(summary_key, title, icon, anchor)`` where ``anchor`` is
#: the in-page ``id`` to scroll to.
MODEL_DETAIL_METRIC_CARDS: tuple[tuple[str, str, str, str], ...] = (
    ("fields",             "Fields",             "bi-input-cursor-text", "section-fields"),
    ("views",              "Views",              "bi-window-stack",      "section-views"),
    ("server_actions",     "Server Actions",     "bi-lightning-charge",  "section-server_actions"),
    ("window_actions",     "Window Actions",     "bi-window",            "section-window_actions"),
    ("menus",              "Menus",              "bi-list-ul",           "section-menus"),
    ("access_rights",      "Access Rights",      "bi-shield-lock",       "section-access_rights"),
    ("record_rules",       "Record Rules",       "bi-shield-shaded",     "section-record_rules"),
    ("outgoing_relations", "Outgoing Relations", "bi-arrow-up-right",    "section-relationships"),
    ("incoming_relations", "Incoming Relations", "bi-arrow-down-left",   "section-relationships"),
)


def build_model_detail_metric_cards(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the metric-strip cards for the model detail page."""
    summary = payload.get("summary", {}) or {}
    return [
        {"key": key, "title": title, "icon": icon, "anchor": anchor, "count": summary.get(key, 0)}
        for key, title, icon, anchor in MODEL_DETAIL_METRIC_CARDS
    ]


def build_model_detail_section_rows(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Pre-render the rows for every model-detail section."""
    sections: list[dict[str, Any]] = []
    for slug, title, icon, payload_key, columns in MODEL_DETAIL_SECTIONS:
        records = payload.get(payload_key) or []
        sections.append(
            {
                "slug": slug,
                "title": title,
                "icon": icon,
                "columns": columns,
                "records": records,
                "rows": build_rows(records, columns),
                "count": len(records),
            }
        )
    # Relationships render as two tables; expose them separately so the
    # template can put both inside one "Relationships" section card.
    outgoing = payload.get("relationships", {}).get("outgoing", []) or []
    incoming = payload.get("relationships", {}).get("incoming", []) or []
    sections.append(
        {
            "slug": "relationships",
            "title": "Relationships",
            "icon": "bi-diagram-3",
            "outgoing": {
                "columns": MODEL_OUTGOING_REL_COLUMNS,
                "records": outgoing,
                "rows": build_rows(outgoing, MODEL_OUTGOING_REL_COLUMNS),
                "count": len(outgoing),
            },
            "incoming": {
                "columns": MODEL_INCOMING_REL_COLUMNS,
                "records": incoming,
                "rows": build_rows(incoming, MODEL_INCOMING_REL_COLUMNS),
                "count": len(incoming),
            },
        }
    )
    return sections


def model_detail_to_json(payload: dict[str, Any]) -> str:
    """Return the model-detail payload as pretty-printed JSON text."""
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def model_detail_to_markdown(
    audit,
    model_name: str,
    payload: dict[str, Any],
) -> str:
    """Return a multi-section Markdown document for one model."""
    lines: list[str] = []
    record = payload.get("model_record") or {}
    instance_name = payload.get("instance_name") or ""
    summary = payload.get("summary") or {}

    lines.append(f"# Odoo Exterior — Model `{model_name}`")
    lines.append("")
    lines.append(f"- **Audit:** #{audit.pk}")
    if instance_name:
        lines.append(f"- **Instance:** {instance_name}")
    display_name = (
        record.get("name") if isinstance(record.get("name"), str) else ""
    )
    if display_name:
        lines.append(f"- **Display name:** {display_name}")
    if record.get("state"):
        lines.append(f"- **State:** {record.get('state')}")
    if record.get("modules"):
        lines.append(f"- **Modules:** {record.get('modules')}")
    lines.append(f"- **Transient:** {'yes' if record.get('transient') else 'no'}")
    lines.append("")

    # Summary block
    lines.append("## Summary")
    lines.append("")
    for key, title, _icon, _anchor in MODEL_DETAIL_METRIC_CARDS:
        lines.append(f"- **{title}:** {summary.get(key, 0)}")
    lines.append("")

    # Tabular sections
    for slug, title, _icon, payload_key, columns in MODEL_DETAIL_SECTIONS:
        records = payload.get(payload_key) or []
        lines.append(f"## {title}")
        lines.append("")
        if not records:
            lines.append("_None._")
            lines.append("")
            continue
        _emit_markdown_table(lines, columns, records)
        lines.append("")

    # Relationships
    relationships = payload.get("relationships") or {}
    outgoing = relationships.get("outgoing") or []
    incoming = relationships.get("incoming") or []

    lines.append("## Outgoing relations")
    lines.append("")
    if outgoing:
        _emit_markdown_table(lines, MODEL_OUTGOING_REL_COLUMNS, outgoing)
    else:
        lines.append("_None._")
    lines.append("")

    lines.append("## Incoming relations")
    lines.append("")
    if incoming:
        _emit_markdown_table(lines, MODEL_INCOMING_REL_COLUMNS, incoming)
    else:
        lines.append("_None._")
    lines.append("")

    return "\n".join(lines)

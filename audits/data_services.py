"""Live Odoo data-fetch helpers for the Model Data Explorer.

This module is the only place that talks to a live Odoo instance from the
Data Explorer code path. It is read-only by construction: it relies on
:class:`odoo_studio_extractor.client.OdooClient`, whose ``_execute`` helper
hard-rejects anything outside ``{search, read, search_read, search_count,
fields_get, default_get}``.

Single responsibilities:

* parse + clamp the user-supplied query parameters,
* derive the list of fields the user may select for a given model from
  the audit JSON (defensive — never trusts the URL),
* build an Odoo domain from a search box + field selector,
* fetch records via ``search_count`` + ``search_read``,
* serialize values for the template / CSV / JSON export,
* hide and report Odoo authentication / connection errors gracefully.

Credentials never leave this module. They are read from the
``OdooInstance`` via the existing :meth:`get_password` helper, passed once
to the extractor's :class:`OdooConfig`, and never logged or returned.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field as _dc_field
from typing import Any, Iterable

from . import explorer

# --------------------------------------------------------------------- #
# Public constants
# --------------------------------------------------------------------- #

#: Allowed values for the ``limit`` query parameter. Anything outside this
#: set is silently snapped to ``DEFAULT_LIMIT``. The page must never let a
#: tampered URL bypass this cap.
ALLOWED_LIMITS: tuple[int, ...] = (50, 100, 500, 1000)
DEFAULT_LIMIT: int = 100
MAX_LIMIT: int = 1000

#: Field ``ttype`` values that are cheap to fetch and easy to render.
SAFE_SCALAR_TYPES: frozenset[str] = frozenset(
    {
        "char", "text", "html", "selection",
        "integer", "float", "monetary",
        "boolean",
        "date", "datetime",
    }
)
SAFE_RELATIONAL_TYPES: frozenset[str] = frozenset({"many2one"})
HEAVY_RELATIONAL_TYPES: frozenset[str] = frozenset({"many2many", "one2many"})

#: Types we always exclude (binary blobs etc).
EXCLUDED_TYPES: frozenset[str] = frozenset({"binary"})

#: Field types we'll search through with an ``ilike`` clause when the user
#: types in the search box.
ILIKE_TYPES: frozenset[str] = frozenset(
    {"char", "text", "html", "selection", "many2one"}
)

#: Always-available synthetic fields. Odoo exposes ``id`` on every model
#: and ``display_name`` on every regular model.
ALWAYS_AVAILABLE_FIELDS: tuple[dict[str, Any], ...] = (
    {"name": "id", "label": "ID", "ttype": "integer", "is_safe": True, "is_default": True, "synthetic": True},
    {"name": "display_name", "label": "Display name", "ttype": "char", "is_safe": True, "is_default": True, "synthetic": True},
)

#: Built-in metadata fields we surface as selectable on every model.
COMMON_METADATA_FIELDS: tuple[dict[str, Any], ...] = (
    {"name": "create_date", "label": "Created", "ttype": "datetime", "is_safe": True, "is_default": True, "synthetic": True},
    {"name": "write_date", "label": "Last updated", "ttype": "datetime", "is_safe": True, "is_default": True, "synthetic": True},
)

#: Supported export formats for the Data Explorer.
DATA_EXPORT_FORMATS: tuple[str, ...] = ("json", "csv")


# --------------------------------------------------------------------- #
# Fields catalogue (derived from the audit, never from user input)
# --------------------------------------------------------------------- #

def get_model_available_fields(audit, model_name: str) -> list[dict[str, Any]]:
    """Return the list of fields the user may pick on the Data Explorer.

    Built from ``audit.json_report["fields"]`` (the source-of-truth schema
    captured at audit time) plus a handful of synthetic always-on fields
    (``id``, ``display_name``, ``create_date``, ``write_date``).

    Each entry exposes:

    * ``name``      — the technical field name (the only value ever sent
                       back to Odoo)
    * ``label``     — human label for the UI
    * ``ttype``     — Odoo field type
    * ``relation``  — destination model for relational fields, ``""``
                       otherwise
    * ``is_safe``   — ``True`` if the field is cheap to fetch and safe to
                       select by default
    * ``is_default``— ``True`` if the field should be pre-selected on the
                       initial page load
    * ``synthetic`` — ``True`` for the built-in id / display_name / dates
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def _push(item: dict[str, Any]) -> None:
        if item["name"] in seen:
            return
        seen.add(item["name"])
        out.append(item)

    for entry in ALWAYS_AVAILABLE_FIELDS:
        _push(dict(entry))
    for entry in COMMON_METADATA_FIELDS:
        _push(dict(entry))

    # Studio / extracted fields from the audit
    for f in explorer.get_model_fields(audit, model_name):
        ttype = (f.get("ttype") or "").strip() or "char"
        if ttype in EXCLUDED_TYPES:
            continue
        name = f.get("name")
        if not isinstance(name, str) or not name:
            continue
        is_safe = ttype in (SAFE_SCALAR_TYPES | SAFE_RELATIONAL_TYPES)
        _push(
            {
                "name": name,
                "label": f.get("field_description") or name,
                "ttype": ttype,
                "relation": f.get("relation") or "",
                "is_safe": is_safe,
                # Pre-select only studio scalar fields by default to keep
                # the first round-trip lightweight.
                "is_default": is_safe and ttype != "many2one",
                "synthetic": False,
                "heavy": ttype in HEAVY_RELATIONAL_TYPES,
            }
        )
    return out


def get_default_data_fields(audit, model_name: str) -> list[str]:
    """Return the list of field names selected when the page first loads."""
    return [f["name"] for f in get_model_available_fields(audit, model_name) if f.get("is_default")]


def _fields_by_name(available_fields: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {f["name"]: f for f in available_fields}


# --------------------------------------------------------------------- #
# Query parameter parsing & sanitization
# --------------------------------------------------------------------- #

def clamp_limit(raw: Any) -> int:
    """Snap any user input to one of :data:`ALLOWED_LIMITS`."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    if value in ALLOWED_LIMITS:
        return value
    # Tampered query string: clamp into the allowed window. Never trust
    # the URL to give us more than MAX_LIMIT records.
    if value < ALLOWED_LIMITS[0]:
        return ALLOWED_LIMITS[0]
    return MAX_LIMIT


def clamp_offset(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def sanitize_field_selection(
    requested: Iterable[str] | None,
    available_fields: Iterable[dict[str, Any]],
    *,
    defaults: Iterable[str] | None = None,
) -> list[str]:
    """Drop any field name that is not in ``available_fields``.

    Always includes ``id`` (Odoo requires it). Returns the ``defaults``
    list if the user supplied nothing useful.
    """
    available_names = {f["name"] for f in available_fields}
    keep: list[str] = []
    if requested:
        for name in requested:
            if not isinstance(name, str):
                continue
            name = name.strip()
            if name and name in available_names and name not in keep:
                keep.append(name)
    if not keep:
        keep = [d for d in (defaults or []) if d in available_names]
    if "id" not in keep:
        keep.insert(0, "id")
    return keep


def sanitize_search_field(
    raw: Any,
    available_fields: Iterable[dict[str, Any]],
) -> str:
    """Return the search field name if valid, else ``""``."""
    if not isinstance(raw, str):
        return ""
    raw = raw.strip()
    if not raw:
        return ""
    available_names = {f["name"] for f in available_fields}
    return raw if raw in available_names else ""


# --------------------------------------------------------------------- #
# Domain construction
# --------------------------------------------------------------------- #

def build_odoo_domain(
    search_field: str,
    query: str,
    available_fields: Iterable[dict[str, Any]],
) -> list[Any]:
    """Build a safe Odoo domain from the search box.

    * empty ``query`` -> ``[]``
    * ``id`` field with non-numeric input -> ``[]`` (avoid client errors)
    * ``id`` field with numeric input    -> ``[("id", "=", int(q))]``
    * other ilike-friendly fields        -> ``[(f, "ilike", q)]``
    * other fields (e.g. integer/date)   -> best-effort ``ilike``; Odoo
      may raise an error which the caller catches.
    """
    if not query or not search_field:
        return []
    field_meta = _fields_by_name(available_fields).get(search_field)
    if field_meta is None:
        return []  # never let an unknown field name reach Odoo

    if search_field == "id":
        try:
            return [("id", "=", int(query.strip()))]
        except (TypeError, ValueError):
            return []

    ttype = field_meta.get("ttype") or "char"
    if ttype in ILIKE_TYPES:
        return [(search_field, "ilike", query)]
    # Best-effort fallback for numeric/date types — Odoo accepts ilike on
    # quite a few of them; if not, fetch_model_records swallows the fault.
    return [(search_field, "ilike", query)]


# --------------------------------------------------------------------- #
# Live Odoo fetch
# --------------------------------------------------------------------- #

@dataclass
class FetchResult:
    """Outcome of one Data Explorer query."""

    records: list[dict[str, Any]] = _dc_field(default_factory=list)
    total: int = 0
    fields_used: list[str] = _dc_field(default_factory=list)
    error: str = ""
    has_more: bool = False

    @property
    def ok(self) -> bool:
        return not self.error


def fetch_model_records(
    audit,
    model_name: str,
    *,
    fields: list[str],
    limit: int,
    offset: int,
    search_field: str = "",
    query: str = "",
) -> FetchResult:
    """Run ``search_count`` + ``search_read`` against the instance's Odoo.

    All Odoo errors are translated into :class:`FetchResult` with a
    friendly ``error`` message. Credentials are read from the
    ``OdooInstance`` via :meth:`get_password` and never returned.
    """
    # Defensive caps — the view already clamps, but never trust the caller.
    limit = clamp_limit(limit)
    offset = clamp_offset(offset)

    available = get_model_available_fields(audit, model_name)
    safe_fields = sanitize_field_selection(
        fields, available, defaults=get_default_data_fields(audit, model_name)
    )
    domain = build_odoo_domain(search_field, query, available)

    # Lazy import: keeps the extractor out of normal startup.
    try:
        from .services import _build_client  # internal but same-app reuse
        from odoo_studio_extractor.client import (
            OdooAuthenticationError,
            OdooConnectionError,
            OdooClientError,
        )
    except Exception as exc:  # pragma: no cover - environment-level failure
        return FetchResult(
            records=[], total=0, fields_used=safe_fields,
            error=f"Could not load the Odoo client: {exc.__class__.__name__}.",
        )

    instance = audit.instance
    try:
        client = _build_client(instance)
        client.authenticate()
        total = client.count(model_name, domain)
        records = client.search_read(
            model_name,
            domain=domain,
            fields=safe_fields,
            limit=limit,
            offset=offset,
            order="id desc",
        )
    except OdooAuthenticationError as exc:
        return FetchResult(
            fields_used=safe_fields,
            error=f"Authentication failed: {exc}",
        )
    except OdooConnectionError as exc:
        return FetchResult(
            fields_used=safe_fields,
            error=f"Could not reach Odoo: {exc}",
        )
    except OdooClientError as exc:
        # Most "Access denied" / "Field doesn't exist" errors land here.
        return FetchResult(
            fields_used=safe_fields,
            error=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensive
        return FetchResult(
            fields_used=safe_fields,
            error=f"Unexpected error ({exc.__class__.__name__}).",
        )

    return FetchResult(
        records=list(records),
        total=int(total),
        fields_used=safe_fields,
        has_more=(offset + len(records)) < int(total),
    )


# --------------------------------------------------------------------- #
# Value rendering
# --------------------------------------------------------------------- #

_DEFAULT_CELL_LIMIT = 80


def _truncate(text: str, limit: int = _DEFAULT_CELL_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def serialize_record_value(value: Any) -> str:
    """Flat string serialization used for CSV/JSON-fallback rendering."""
    if value is None or value is False:
        return ""
    if isinstance(value, (list, tuple)) and len(value) == 2 and isinstance(value[0], int) and isinstance(value[1], str):
        return value[1]
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def render_data_cell(value: Any, ttype: str | None) -> dict[str, Any]:
    """Pre-render one Data Explorer cell for the template.

    Returns the same shape as the explorer cells (``display``, ``title``,
    ``kind``, ``bool``, ``empty``) so the template can reuse the existing
    table styles.
    """
    ttype = (ttype or "").strip()

    # Booleans as pills
    if ttype == "boolean":
        b = bool(value)
        return {"display": "true" if b else "false",
                "title": "true" if b else "false",
                "kind": "bool", "bool": b, "empty": False}

    # Empty / "Odoo false"
    if value is None or value is False:
        return {"display": "", "title": "", "kind": "empty", "bool": None, "empty": True}

    # Many2one tuple [id, "name"]
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], int)
        and isinstance(value[1], str)
    ):
        text = value[1]
        return {"display": _truncate(text), "title": text,
                "kind": "code", "bool": None, "empty": False}

    # Collections: m2m / o2m / list-of-ids — show a compact count
    if isinstance(value, (list, tuple)):
        n = len(value)
        if n == 0:
            return {"display": "", "title": "", "kind": "empty", "bool": None, "empty": True}
        if all(isinstance(v, int) for v in value):
            text = f"{n} record(s)"
            return {"display": text, "title": ", ".join(str(v) for v in value),
                    "kind": "badge", "bool": None, "empty": False}
        # Mixed list
        text = ", ".join(serialize_record_value(v) for v in value if serialize_record_value(v))
        return {"display": _truncate(text), "title": text,
                "kind": "text", "bool": None, "empty": False}

    if isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False, default=str)
        return {"display": _truncate(text, 120), "title": text,
                "kind": "preview", "bool": None, "empty": False}

    text = str(value)
    kind = "code" if ttype in {"char", "selection"} and len(text) < 40 else "text"
    return {"display": _truncate(text), "title": text,
            "kind": kind, "bool": None, "empty": False}


def build_data_rows(
    records: Iterable[dict[str, Any]],
    fields: Iterable[str],
    available_fields: Iterable[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Pre-render rows for the Data Explorer table."""
    fname_to_ttype = {f["name"]: f.get("ttype") for f in available_fields}
    fields = list(fields)
    return [
        [render_data_cell(rec.get(name), fname_to_ttype.get(name)) for name in fields]
        for rec in records
    ]


# --------------------------------------------------------------------- #
# Serializers for the export endpoint
# --------------------------------------------------------------------- #

def records_to_json(records: Iterable[dict[str, Any]]) -> str:
    """Return records as pretty-printed JSON (raw Odoo wire format preserved)."""
    return json.dumps(list(records), indent=2, ensure_ascii=False, default=str)


def records_to_csv(
    records: Iterable[dict[str, Any]],
    fields: Iterable[str],
) -> str:
    """Return a CSV document with the chosen ``fields`` as header columns.

    Values are flattened with :func:`serialize_record_value`, so m2o
    tuples collapse to the display name, m2m lists collapse to a
    comma-separated string, etc.
    """
    fields = list(fields)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(fields)
    for record in records:
        writer.writerow([serialize_record_value(record.get(f)) for f in fields])
    return buffer.getvalue()

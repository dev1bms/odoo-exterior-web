"""Service layer wrapping the ``odoo-studio-extractor`` engine.

This module is the only place that imports the extractor package, so the
rest of the Django code stays independent of it. To move audit execution
off the request cycle later (e.g. Celery), replace the body of
:func:`run_studio_audit` with an enqueue call and run the same logic in a
worker.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

from django.utils import timezone as djtz

from odoo_studio_extractor import __version__ as _extractor_version
from odoo_studio_extractor.client import (
    OdooAuthenticationError,
    OdooClient,
    OdooClientError,
    OdooConnectionError,
)
from odoo_studio_extractor.config import OdooConfig
from odoo_studio_extractor.extractors import (
    extract_access_rights,
    extract_automations,
    extract_fields,
    extract_menus,
    extract_models,
    extract_record_rules,
    extract_server_actions,
    extract_views,
    extract_window_actions,
)
from odoo_studio_extractor.reports.markdown import render_markdown_report

from instances.models import OdooInstance

from .models import AuditRun


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def _build_client(instance: OdooInstance) -> OdooClient:
    config = OdooConfig(
        url=instance.odoo_url,
        db=instance.database,
        username=instance.username,
        password=instance.get_password(),
    )
    return OdooClient(config)


def _update_connection_status(
    instance: OdooInstance,
    status: str,
    error: str = "",
) -> None:
    instance.last_connection_status = status
    instance.last_connection_error = error
    instance.save(
        update_fields=[
            "last_connection_status",
            "last_connection_error",
            "updated_at",
        ]
    )


# ---------------------------------------------------------------------- #
# Public API
# ---------------------------------------------------------------------- #
def test_odoo_connection(instance: OdooInstance) -> Tuple[bool, str]:
    """Authenticate against Odoo and persist the result on the instance.

    Returns ``(ok, error_message)``. The error message is empty on success.
    """
    client = _build_client(instance)
    try:
        client.authenticate()
    except OdooAuthenticationError as exc:
        _update_connection_status(
            instance, OdooInstance.ConnectionStatus.AUTH_FAILED, str(exc)
        )
        return False, str(exc)
    except OdooConnectionError as exc:
        _update_connection_status(
            instance, OdooInstance.ConnectionStatus.CONNECTION_FAILED, str(exc)
        )
        return False, str(exc)
    except OdooClientError as exc:
        _update_connection_status(
            instance, OdooInstance.ConnectionStatus.ERROR, str(exc)
        )
        return False, str(exc)

    _update_connection_status(instance, OdooInstance.ConnectionStatus.OK, "")
    return True, ""


def run_studio_audit(instance: OdooInstance) -> AuditRun:
    """Synchronously run a full Studio audit and persist the result.

    The function always returns an :class:`AuditRun`. On failure, the run's
    ``status`` is ``FAILED`` and ``error_message`` is populated.
    """
    run = AuditRun.objects.create(
        instance=instance,
        status=AuditRun.Status.RUNNING,
        started_at=djtz.now(),
    )
    try:
        data, warnings, summary = _execute_extraction(instance)
        run.summary = summary
        run.warnings = warnings
        run.markdown_report = render_markdown_report(data)
        run.json_report = data
        run.status = AuditRun.Status.COMPLETED
        run.finished_at = djtz.now()
        run.save()

        # Reflect the successful authentication in the instance state.
        _update_connection_status(instance, OdooInstance.ConnectionStatus.OK, "")

    except OdooAuthenticationError as exc:
        run.status = AuditRun.Status.FAILED
        run.finished_at = djtz.now()
        run.error_message = f"Authentication failed: {exc}"
        run.save()
        _update_connection_status(
            instance, OdooInstance.ConnectionStatus.AUTH_FAILED, str(exc)
        )
    except OdooConnectionError as exc:
        run.status = AuditRun.Status.FAILED
        run.finished_at = djtz.now()
        run.error_message = f"Connection error: {exc}"
        run.save()
        _update_connection_status(
            instance, OdooInstance.ConnectionStatus.CONNECTION_FAILED, str(exc)
        )
    except OdooClientError as exc:
        run.status = AuditRun.Status.FAILED
        run.finished_at = djtz.now()
        run.error_message = f"Odoo client error: {exc}"
        run.save()
        _update_connection_status(
            instance, OdooInstance.ConnectionStatus.ERROR, str(exc)
        )
    except Exception as exc:  # pragma: no cover - defensive
        run.status = AuditRun.Status.FAILED
        run.finished_at = djtz.now()
        run.error_message = f"Unexpected error: {exc.__class__.__name__}: {exc}"
        run.save()

    return run


# ---------------------------------------------------------------------- #
# Internals
# ---------------------------------------------------------------------- #
def _execute_extraction(instance: OdooInstance) -> tuple[dict, list[str], dict[str, int]]:
    client = _build_client(instance)
    client.authenticate()

    warnings: list[str] = []

    models = extract_models(client, warnings)
    custom_model_names = [m["model"] for m in models if m.get("model")]

    fields = extract_fields(client, warnings, extra_models=custom_model_names)

    models_with_studio_fields = sorted(
        {f.get("model") for f in fields if f.get("model")}
    )
    interesting_models = sorted(
        set(custom_model_names) | set(models_with_studio_fields)
    )

    views = extract_views(client, warnings, custom_models=interesting_models)
    server_actions = extract_server_actions(
        client, warnings, custom_models=interesting_models
    )
    automations = extract_automations(
        client, warnings, custom_models=interesting_models
    )
    window_actions = extract_window_actions(
        client, warnings, custom_models=interesting_models
    )
    menus = extract_menus(
        client,
        warnings,
        window_action_ids=[a["id"] for a in window_actions if a.get("id")],
    )
    access_rights = extract_access_rights(
        client, warnings, custom_models=interesting_models
    )
    record_rules = extract_record_rules(
        client, warnings, custom_models=interesting_models
    )

    data = {
        "metadata": {
            "tool": "odoo-studio-extractor",
            "tool_version": _extractor_version,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "odoo_url": instance.odoo_url,
            "odoo_db": instance.database,
            "odoo_user": instance.username,
            "warnings": warnings,
            "interesting_models": interesting_models,
        },
        "models": models,
        "fields": fields,
        "views": views,
        "server_actions": server_actions,
        "automations": automations,
        "menus": menus,
        "window_actions": window_actions,
        "access_rights": access_rights,
        "record_rules": record_rules,
    }

    summary = {
        "models": len(models),
        "fields": len(fields),
        "views": len(views),
        "server_actions": len(server_actions),
        "automations": len(automations),
        "menus": len(menus),
        "window_actions": len(window_actions),
        "access_rights": len(access_rights),
        "record_rules": len(record_rules),
    }

    return data, warnings, summary

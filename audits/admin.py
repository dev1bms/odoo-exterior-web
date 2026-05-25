from django.contrib import admin

from .models import AuditRun


@admin.register(AuditRun)
class AuditRunAdmin(admin.ModelAdmin):
    list_display = ("id", "instance", "status", "created_at", "finished_at")
    list_filter = ("status",)
    search_fields = ("instance__name", "instance__user__username", "error_message")
    readonly_fields = (
        "instance",
        "status",
        "started_at",
        "finished_at",
        "summary",
        "warnings",
        "error_message",
        "markdown_report",
        "json_report",
        "created_at",
    )

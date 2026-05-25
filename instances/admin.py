from django.contrib import admin

from .models import OdooInstance


@admin.register(OdooInstance)
class OdooInstanceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "user",
        "odoo_url",
        "database",
        "username",
        "is_active",
        "last_connection_status",
        "updated_at",
    )
    list_filter = ("is_active", "last_connection_status")
    search_fields = ("name", "odoo_url", "database", "username", "user__username")
    readonly_fields = (
        "encrypted_password",
        "last_connection_status",
        "last_connection_error",
        "created_at",
        "updated_at",
    )

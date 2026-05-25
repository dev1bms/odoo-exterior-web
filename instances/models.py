"""Database models for the instances app."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse

from .crypto import decrypt, encrypt


class OdooInstance(models.Model):
    """A user-registered Odoo instance to audit.

    The password is never stored in plaintext: callers must use
    :py:meth:`set_password` / :py:meth:`get_password`.
    """

    class ConnectionStatus(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        OK = "ok", "OK"
        AUTH_FAILED = "auth_failed", "Authentication failed"
        CONNECTION_FAILED = "connection_failed", "Connection failed"
        ERROR = "error", "Error"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="odoo_instances",
    )
    name = models.CharField(max_length=120)
    odoo_url = models.URLField(max_length=300)
    database = models.CharField(max_length=120)
    username = models.CharField(max_length=200)
    encrypted_password = models.TextField()
    version = models.CharField(max_length=50, blank=True, default="")
    is_active = models.BooleanField(default=True)
    last_connection_status = models.CharField(
        max_length=32,
        choices=ConnectionStatus.choices,
        default=ConnectionStatus.UNKNOWN,
    )
    last_connection_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "name"),
                name="unique_instance_name_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.odoo_url})"

    # ------------------------------------------------------------------ #
    # Password handling
    # ------------------------------------------------------------------ #
    def set_password(self, plaintext: str) -> None:
        """Encrypt and store ``plaintext`` in ``encrypted_password``."""
        self.encrypted_password = encrypt(plaintext or "")

    def get_password(self) -> str:
        """Return the decrypted password. Never log or render this value."""
        return decrypt(self.encrypted_password or "")

    # ------------------------------------------------------------------ #
    # URL helpers
    # ------------------------------------------------------------------ #
    def get_absolute_url(self) -> str:
        return reverse("instances:detail", kwargs={"pk": self.pk})

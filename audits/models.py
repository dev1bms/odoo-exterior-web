"""Database models for the audits app."""

from __future__ import annotations

from django.db import models
from django.urls import reverse


class AuditRun(models.Model):
    """A single run of a Studio audit against an OdooInstance."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    instance = models.ForeignKey(
        "instances.OdooInstance",
        on_delete=models.CASCADE,
        related_name="audits",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    summary = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True, default="")

    markdown_report = models.TextField(blank=True, default="")
    json_report = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"AuditRun #{self.pk} — {self.instance.name} [{self.status}]"

    def get_absolute_url(self) -> str:
        return reverse("audits:detail", kwargs={"pk": self.pk})

    @property
    def is_terminal(self) -> bool:
        return self.status in {self.Status.COMPLETED, self.Status.FAILED}

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

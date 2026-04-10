"""Sink contracts for publishing canonical artifacts."""

from __future__ import annotations

from typing import Protocol

from app.artifacts.models import ArtifactBundle
from app.models.results import VaultUpdate
from app.models.source import SourceContent


class ArtifactSink(Protocol):
    """Publish canonical artifacts into a concrete output target."""

    sink_id: str

    def publish(
        self,
        *,
        content: SourceContent,
        bundle: ArtifactBundle,
    ) -> list[VaultUpdate]:
        """Publish canonical artifacts and return durable note updates."""

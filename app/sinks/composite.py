"""Composite sink support for publishing to multiple sinks."""

from __future__ import annotations

from app.artifacts.models import ArtifactBundle
from app.models.results import VaultUpdate
from app.models.source import SourceContent
from app.sinks.base import ArtifactSink


class CompositeSink:
    """Publish a bundle through multiple sinks in a deterministic order."""

    sink_id = "composite"

    def __init__(self, sinks: list[ArtifactSink]):
        self.sinks = sinks

    def publish(
        self,
        *,
        content: SourceContent,
        bundle: ArtifactBundle,
    ) -> list[VaultUpdate]:
        updates: list[VaultUpdate] = []
        for sink in self.sinks:
            updates.extend(sink.publish(content=content, bundle=bundle))
        return updates

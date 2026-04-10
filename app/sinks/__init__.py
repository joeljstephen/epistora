"""Artifact sink interfaces and implementations."""

from app.sinks.base import ArtifactSink
from app.sinks.composite import CompositeSink
from app.sinks.json_export import JsonExportSink
from app.sinks.markdown_vault import MarkdownVaultSink
from app.sinks.registry import available_sink_ids, build_default_sink, build_sink

__all__ = [
    "ArtifactSink",
    "CompositeSink",
    "JsonExportSink",
    "MarkdownVaultSink",
    "available_sink_ids",
    "build_default_sink",
    "build_sink",
]

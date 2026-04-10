"""Deterministic JSON export sink for canonical artifact bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.artifacts.models import ArtifactBundle
from app.models.results import VaultUpdate
from app.models.source import SourceContent


class JsonExportSink:
    """Publish canonical artifacts as structured JSON for machine-facing use."""

    sink_id = "json_export"
    schema_version = "epistora.json_export.v1"

    def __init__(self, vault_path: Path, export_root: Path):
        self.vault_path = vault_path
        self.export_root = export_root

    def publish(
        self,
        *,
        content: SourceContent,
        bundle: ArtifactBundle,
    ) -> list[VaultUpdate]:
        del content

        path = self.export_root / bundle.source.source_type / f"{bundle.source.slug}.json"
        payload = self._export_payload(bundle)
        serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"

        action = "updated" if path.exists() else "created"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized, encoding="utf-8")

        return [
            VaultUpdate(
                path=self._display_path(path),
                action=action,
                note_type="json_export",
            )
        ]

    def _export_payload(self, bundle: ArtifactBundle) -> dict[str, Any]:
        return {
            "artifact_counts": {
                "concepts": len(bundle.concepts),
                "entities": len(bundle.entities),
                "evidence_references": len(bundle.evidence_references),
                "relationships": len(bundle.relationships),
                "synthesis": len(bundle.synthesis),
                "topics": len(bundle.topics),
            },
            "bundle": {
                "concepts": self._sorted_models(bundle.concepts),
                "entities": self._sorted_models(bundle.entities),
                "evidence_references": self._sorted_models(bundle.evidence_references),
                "relationships": self._sorted_models(bundle.relationships),
                "source": bundle.source.model_dump(mode="json"),
                "synthesis": self._sorted_models(bundle.synthesis),
                "topics": self._sorted_models(bundle.topics),
            },
            "export": {
                "sink_id": self.sink_id,
                "source_artifact_id": bundle.source.id,
                "source_slug": bundle.source.slug,
                "source_type": bundle.source.source_type,
            },
            "schema_version": self.schema_version,
        }

    @staticmethod
    def _sorted_models(models: list[Any]) -> list[dict[str, Any]]:
        return [
            model.model_dump(mode="json")
            for model in sorted(models, key=lambda item: getattr(item, "id", ""))
        ]

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.vault_path))
        except ValueError:
            return str(path)

"""Backward-compatible wrapper around the markdown vault sink."""

from __future__ import annotations

from pathlib import Path

from app.sinks.markdown_vault import MarkdownVaultSink
from app.storage.evidence import EvidenceStoragePolicy


class VaultWriter(MarkdownVaultSink):
    """Compatibility alias for tests and helper code that still import VaultWriter."""

    def __init__(
        self,
        vault_path: Path,
        *,
        storage_policy: EvidenceStoragePolicy | None = None,
    ):
        super().__init__(vault_path, storage_policy=storage_policy)

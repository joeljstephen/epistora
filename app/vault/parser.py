"""Parse vault markdown files for retrieval and indexing."""

from __future__ import annotations

from pathlib import Path

from app.utils.markdown import extract_wikilinks, parse_markdown_file


class VaultNote:
    def __init__(self, path: Path, vault_root: Path):
        self.path = path
        self.vault_root = vault_root
        self.rel_path = str(path.relative_to(vault_root))
        self._meta: dict | None = None
        self._body: str | None = None

    def _load(self) -> None:
        if self._meta is None:
            self._meta, self._body = parse_markdown_file(self.path)

    @property
    def meta(self) -> dict:
        self._load()
        return self._meta  # type: ignore

    @property
    def body(self) -> str:
        self._load()
        return self._body  # type: ignore

    @property
    def title(self) -> str:
        return self.meta.get("title", self.path.stem)

    @property
    def note_type(self) -> str:
        return self.meta.get("type", self._infer_type())

    @property
    def tags(self) -> list[str]:
        return self.meta.get("tags", [])

    @property
    def topics(self) -> list[str]:
        return self.meta.get("topics", [])

    @property
    def outgoing_links(self) -> list[str]:
        return extract_wikilinks(self.body)

    def _infer_type(self) -> str:
        if self.path.name == "AGENTS.md":
            return "system"
        if "wiki/indexes/" in self.rel_path:
            return "index"
        if "wiki/logs/" in self.rel_path:
            return "log"
        if "wiki/sources/" in self.rel_path:
            return "source"
        if "wiki/topics/" in self.rel_path:
            return "topic"
        if "wiki/entities/" in self.rel_path:
            return "entity"
        if "wiki/concepts/" in self.rel_path:
            return "concept"
        if "wiki/synthesis/" in self.rel_path:
            return "synthesis"
        if "inbox/raw/" in self.rel_path:
            return "raw"
        return "unknown"


def scan_vault(vault_path: Path) -> list[VaultNote]:
    notes: list[VaultNote] = []
    for md_file in vault_path.rglob("*.md"):
        if md_file.name.startswith(".") or ".system" in md_file.parts:
            continue
        notes.append(VaultNote(md_file, vault_path))
    return notes

"""Planning logic for bounded maintenance runs."""

from __future__ import annotations

from pathlib import Path

from app.automation.models import AutomationMode
from app.maintenance.models import MaintenanceClass, MaintenancePlan, MaintenanceTask
from app.read_model.store import (
    RELATION_SOURCE_CONCEPT,
    RELATION_SOURCE_ENTITY,
    RELATION_SOURCE_TOPIC,
    ReadModelStore,
)

_HUB_TYPES = {"topic", "entity", "concept"}
_SOURCE_RELATIONS = {
    RELATION_SOURCE_TOPIC,
    RELATION_SOURCE_ENTITY,
    RELATION_SOURCE_CONCEPT,
}


class MaintenancePlanner:
    """Plan maintenance tasks from mode and scope."""

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.read_model = ReadModelStore(vault_path)

    def plan(
        self,
        *,
        mode: str,
        scope_paths: list[str] | None = None,
        force_rebuild: bool = False,
    ) -> MaintenancePlan:
        normalized_scope = sorted(
            {
                path
                for path in (scope_paths or [])
                if path.endswith(".md") and ".system/" not in path
            }
        )
        neighborhood = self._expand_scope(normalized_scope, mode)
        hub_paths = self._hub_paths(neighborhood)
        synthesis_topics = self._topic_paths(neighborhood)

        tasks = [
            MaintenanceTask(
                maintenance_class=MaintenanceClass.STRUCTURAL,
                task_name="structural_audit",
                scope_paths=normalized_scope,
            ),
        ]

        if mode in {AutomationMode.BALANCED, AutomationMode.DEEP} and hub_paths:
            tasks.append(
                MaintenanceTask(
                    maintenance_class=MaintenanceClass.SEMANTIC,
                    task_name="refresh_hub_pages",
                    scope_paths=hub_paths,
                    max_items=12 if mode == AutomationMode.BALANCED else 20,
                )
            )

        if mode == AutomationMode.DEEP:
            tasks.append(
                MaintenanceTask(
                    maintenance_class=MaintenanceClass.SYNTHESIS,
                    task_name="generate_synthesis_candidates",
                    scope_paths=synthesis_topics,
                    max_items=3,
                )
            )

        tasks.append(
            MaintenanceTask(
                maintenance_class=MaintenanceClass.STRUCTURAL,
                task_name="refresh_indexes",
                scope_paths=hub_paths or normalized_scope,
            )
        )

        storage_strategy = "full" if mode == AutomationMode.DEEP or force_rebuild else "incremental"
        tasks.append(
            MaintenanceTask(
                maintenance_class=MaintenanceClass.STORAGE,
                task_name="refresh_read_model",
                scope_paths=neighborhood or normalized_scope,
                details={"strategy": storage_strategy},
            )
        )
        if mode == AutomationMode.DEEP or force_rebuild:
            tasks.append(
                MaintenanceTask(
                    maintenance_class=MaintenanceClass.STORAGE,
                    task_name="refresh_search_index",
                    scope_paths=neighborhood or normalized_scope,
                )
            )

        return MaintenancePlan(
            mode=mode,
            scope_paths=normalized_scope,
            neighborhood_paths=neighborhood,
            tasks=tasks,
        )

    def _expand_scope(self, scope_paths: list[str], mode: str) -> list[str]:
        if not scope_paths:
            if mode == AutomationMode.DEEP:
                return self._thin_hub_paths(limit=8)
            return []

        neighborhood: set[str] = set(scope_paths)
        for scope_path in scope_paths:
            note = self.read_model.get_note(scope_path)
            if note is None:
                continue

            if note.note_type == "source":
                for edge in self.read_model.get_related_for_source(scope_path):
                    if edge.relation_type in _SOURCE_RELATIONS and edge.to_note_path:
                        neighborhood.add(edge.to_note_path)
            elif note.note_type in _HUB_TYPES:
                for edge in self.read_model.get_backlinks(scope_path):
                    if edge.from_note_path:
                        neighborhood.add(edge.from_note_path)

        if mode == AutomationMode.DEEP:
            second_degree = set(neighborhood)
            for note_path in list(neighborhood):
                note = self.read_model.get_note(note_path)
                if note is None:
                    continue
                if note.note_type == "source":
                    for edge in self.read_model.get_related_for_source(note_path):
                        if edge.to_note_path:
                            second_degree.add(edge.to_note_path)
                elif note.note_type in _HUB_TYPES:
                    for edge in self.read_model.get_backlinks(note_path):
                        if edge.from_note_path:
                            second_degree.add(edge.from_note_path)
            neighborhood = second_degree

        return sorted(neighborhood)

    def _hub_paths(self, neighborhood_paths: list[str]) -> list[str]:
        hub_paths: list[str] = []
        for note_path in neighborhood_paths:
            note = self.read_model.get_note(note_path)
            if note and note.note_type in _HUB_TYPES:
                hub_paths.append(note_path)
        return sorted(dict.fromkeys(hub_paths))

    def _topic_paths(self, neighborhood_paths: list[str]) -> list[str]:
        topic_paths: list[str] = []
        for note_path in neighborhood_paths:
            note = self.read_model.get_note(note_path)
            if note and note.note_type == "topic":
                topic_paths.append(note_path)
        return sorted(dict.fromkeys(topic_paths))

    def _thin_hub_paths(self, *, limit: int) -> list[str]:
        notes = self.read_model.list_notes(limit=500)
        thin: list[str] = []
        for note in notes:
            if note.note_type not in _HUB_TYPES:
                continue
            backlinks = len(self.read_model.get_backlinks(note.note_path))
            if backlinks < 2:
                thin.append(note.note_path)
            if len(thin) >= limit:
                break
        return thin

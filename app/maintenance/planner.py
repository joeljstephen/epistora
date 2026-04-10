"""Planning logic for bounded maintenance runs."""

from __future__ import annotations

from pathlib import Path

from app.automation.models import AutomationMode
from app.maintenance.models import (
    MaintenanceClass,
    MaintenancePlan,
    MaintenanceTask,
    MaintenanceTaskName,
    MaintenanceTrigger,
)
from app.read_model.store import (
    RELATION_CONCEPT_RELATIONSHIP,
    RELATION_ENTITY_MENTION,
    RELATION_SOURCE_SUPPORT,
    RELATION_TOPIC_MEMBERSHIP,
    ReadModelStore,
)

_HUB_TYPES = {"topic", "entity", "concept"}
_SOURCE_FORWARD_RELATIONS = {
    RELATION_TOPIC_MEMBERSHIP,
    RELATION_ENTITY_MENTION,
    RELATION_CONCEPT_RELATIONSHIP,
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
        self.read_model.ensure_populated()
        normalized_scope = sorted(
            {
                path
                for path in (scope_paths or [])
                if path.endswith(".md") and ".system/" not in path
            }
        )
        neighborhood = self._expand_scope(normalized_scope, mode)
        hub_paths = self._hub_paths(neighborhood)
        topic_paths = self._topic_paths(neighborhood)
        trigger = self._trigger_for(
            mode=mode,
            normalized_scope=normalized_scope,
            force_rebuild=force_rebuild,
        )

        tasks = [
            MaintenanceTask(
                maintenance_class=MaintenanceClass.STRUCTURAL,
                task_name=MaintenanceTaskName.ARTIFACT_NEIGHBORHOOD_REFRESH,
                trigger=trigger,
                scope_paths=normalized_scope,
                writes_enabled=False,
                write_scope="none",
                details={
                    "neighborhood_paths": neighborhood,
                    "depth": 2 if mode == AutomationMode.DEEP else 1,
                },
            ),
            MaintenanceTask(
                maintenance_class=MaintenanceClass.STRUCTURAL,
                task_name=MaintenanceTaskName.STRUCTURAL_REPAIR,
                trigger=trigger,
                scope_paths=normalized_scope,
                writes_enabled=True,
                write_scope="wiki/indexes and maintenance-managed frontmatter only",
            ),
        ]

        if mode in {AutomationMode.BALANCED, AutomationMode.DEEP} and hub_paths:
            tasks.append(
                MaintenanceTask(
                    maintenance_class=MaintenanceClass.SEMANTIC,
                    task_name=MaintenanceTaskName.HUB_REFRESH,
                    trigger=trigger,
                    scope_paths=hub_paths,
                    max_items=12 if mode == AutomationMode.BALANCED else 20,
                    writes_enabled=True,
                    write_scope="maintenance-managed hub sections excluding backlinks",
                )
            )
            tasks.append(
                MaintenanceTask(
                    maintenance_class=MaintenanceClass.SEMANTIC,
                    task_name=MaintenanceTaskName.BACKLINK_REPAIR,
                    trigger=trigger,
                    scope_paths=hub_paths,
                    max_items=12 if mode == AutomationMode.BALANCED else 20,
                    writes_enabled=True,
                    write_scope="Backlinks sections on touched hub pages only",
                )
            )

        if mode == AutomationMode.DEEP and topic_paths:
            tasks.append(
                MaintenanceTask(
                    maintenance_class=MaintenanceClass.SYNTHESIS,
                    task_name=MaintenanceTaskName.CANDIDATE_SYNTHESIS_REFRESH,
                    trigger=MaintenanceTrigger.DEEP_MODE,
                    scope_paths=topic_paths,
                    max_items=3,
                    writes_enabled=True,
                    write_scope="candidate synthesis notes under wiki/synthesis only",
                )
            )

        refresh_scope = neighborhood or normalized_scope
        storage_trigger = MaintenanceTrigger.FORCE_REBUILD if force_rebuild else trigger
        tasks.append(
            MaintenanceTask(
                maintenance_class=MaintenanceClass.STORAGE,
                task_name=MaintenanceTaskName.READ_MODEL_REFRESH,
                trigger=storage_trigger,
                scope_paths=refresh_scope,
                writes_enabled=True,
                write_scope="derived read-model DB only",
                details={
                    "strategy": (
                        "full"
                        if mode == AutomationMode.DEEP or force_rebuild
                        else "incremental"
                    )
                },
            )
        )
        tasks.append(
            MaintenanceTask(
                maintenance_class=MaintenanceClass.STORAGE,
                task_name=MaintenanceTaskName.SEARCH_REFRESH,
                trigger=storage_trigger,
                scope_paths=refresh_scope,
                writes_enabled=True,
                write_scope="integrated lexical state inside read-model DB only",
                details={
                    "search_backend": "read_model_fts",
                    "retire_legacy_search_db": True,
                },
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
                    if edge.relation_type in _SOURCE_FORWARD_RELATIONS and edge.to_note_path:
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
                    for edge in self.read_model.get_edges(
                        from_note_path=note_path,
                        relation_type=RELATION_SOURCE_SUPPORT,
                    ):
                        if edge.to_note_path:
                            second_degree.add(edge.to_note_path)
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

    def _trigger_for(
        self,
        *,
        mode: str,
        normalized_scope: list[str],
        force_rebuild: bool,
    ) -> str:
        if force_rebuild:
            return MaintenanceTrigger.FORCE_REBUILD
        if mode == AutomationMode.DEEP:
            return MaintenanceTrigger.DEEP_MODE
        if normalized_scope:
            return MaintenanceTrigger.POST_INGEST
        return MaintenanceTrigger.AUTOMATION_TICK

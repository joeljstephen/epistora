"""Small internal event taxonomy for Epistora runtime hooks."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    SOURCE_INGESTED = "source_ingested"
    ARTIFACT_WRITTEN = "artifact_written"
    MAINTENANCE_COMPLETED = "maintenance_completed"
    QUERY_ANSWER_SAVED = "query_answer_saved"
    SCHEDULED_MAINTENANCE_TICK = "scheduled_maintenance_tick"


class EpistoraEvent(BaseModel):
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)


EventHandler = Callable[[EpistoraEvent], None]

_subscribers: dict[str, list[EventHandler]] = defaultdict(list)
_wildcard_key = "*"


def subscribe(event_type: EventType | str | None, handler: EventHandler) -> None:
    key = event_type.value if isinstance(event_type, EventType) else event_type or _wildcard_key
    _subscribers[key].append(handler)


def clear_subscribers() -> None:
    _subscribers.clear()


def publish(event_type: EventType | str, **payload: Any) -> EpistoraEvent:
    key = event_type.value if isinstance(event_type, EventType) else str(event_type)
    event = EpistoraEvent(event_type=key, payload=payload)
    for handler in list(_subscribers.get(key, [])) + list(_subscribers.get(_wildcard_key, [])):
        try:
            handler(event)
        except Exception:
            logger.warning("Event handler failed for %s", key, exc_info=True)
    return event

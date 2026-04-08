"""Registry and protocol for pluggable saved-link inbox connectors."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.config import Settings, get_settings
from app.connectors.raindrop import RaindropConnector
from app.models.source import SourceItem


class LinkInboxConnector(Protocol):
    connector_id: str

    def fetch_since(self, since: datetime, limit: int = 100) -> list[SourceItem]:
        """Fetch saved links newer than the provided cursor."""


def build_inbox_connectors(settings: Settings | None = None) -> dict[str, LinkInboxConnector]:
    resolved_settings = settings or get_settings()
    connectors: dict[str, LinkInboxConnector] = {}

    if resolved_settings.raindrop_api_token:
        connectors[RaindropConnector.connector_id] = RaindropConnector(
            api_token=resolved_settings.raindrop_api_token,
            collection_id=resolved_settings.raindrop_collection_id,
        )

    return connectors


def get_inbox_connector(
    connector_id: str,
    settings: Settings | None = None,
) -> LinkInboxConnector:
    connectors = build_inbox_connectors(settings)
    connector = connectors.get(connector_id)
    if connector is None:
        raise ValueError(
            f"Inbox connector '{connector_id}' is not configured or not supported"
        )
    return connector

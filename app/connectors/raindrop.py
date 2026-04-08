"""Raindrop.io connector — fetches saved bookmarks from the Raindrop API."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.connectors.classifier import classify_url
from app.models.source import SourceItem

RAINDROP_API_BASE = "https://api.raindrop.io/rest/v1"


class RaindropConnector:
    connector_id = "raindrop"

    def __init__(self, api_token: str, collection_id: int = 0):
        self._token = api_token
        self._collection_id = collection_id

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def fetch_recent(self, limit: int = 25, page: int = 0) -> list[SourceItem]:
        """Fetch recent raindrops from a collection (0 = all unsorted)."""
        url = f"{RAINDROP_API_BASE}/raindrops/{self._collection_id}"
        params = {
            "sort": "-created",
            "perpage": min(limit, 40),
            "page": page,
        }
        resp = httpx.get(url, headers=self._headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        items: list[SourceItem] = []
        for rd in data.get("items", []):
            link = rd.get("link", "")
            if not link:
                continue
            created = rd.get("created", "")
            saved_at = (
                datetime.fromisoformat(created.replace("Z", "+00:00"))
                if created
                else datetime.now(timezone.utc)
            )
            items.append(
                SourceItem(
                    url=link,
                    title=rd.get("title", ""),
                    source_type=classify_url(link),
                    tags=[t for t in rd.get("tags", [])],
                    saved_at=saved_at,
                    inbox_provider=self.connector_id,
                    external_id=str(rd.get("_id") or ""),
                    provider_metadata={
                        "collection_id": rd.get("collection", {}).get("$id"),
                    },
                    extra={"excerpt": rd.get("excerpt", ""), "domain": rd.get("domain", "")},
                )
            )
        return items

    def fetch_since(self, since: datetime, limit: int = 100) -> list[SourceItem]:
        """Fetch raindrops created after a given timestamp."""
        all_items: list[SourceItem] = []
        page = 0
        while len(all_items) < limit:
            batch = self.fetch_recent(limit=40, page=page)
            if not batch:
                break
            for item in batch:
                if item.saved_at > since:
                    all_items.append(item)
                else:
                    return all_items
            page += 1
        return all_items[:limit]

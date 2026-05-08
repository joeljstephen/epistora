"""Readwise Reader connector for extracted document content."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.connectors.classifier import classify_url
from app.models.source import (
    ExtractionQuality,
    PreExtractedSourceContent,
    ProviderContentMode,
    SourceItem,
    SourceType,
)

READWISE_READER_API_BASE = "https://readwise.io/api/v3"


class ReadwiseConnector:
    connector_id = "readwise"

    def __init__(self, api_token: str):
        self._token = api_token

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self._token}"}

    def fetch_since(self, since: datetime, limit: int = 100) -> list[SourceItem]:
        items: list[SourceItem] = []
        page_cursor = ""
        remaining = max(limit, 0)
        while remaining > 0:
            params: dict[str, Any] = {
                "updatedAfter": since.isoformat(),
                "limit": min(remaining, 100),
                "withHtmlContent": "true",
            }
            if page_cursor:
                params["pageCursor"] = page_cursor

            try:
                response = httpx.get(
                    f"{READWISE_READER_API_BASE}/list/",
                    headers=self._headers,
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in {401, 403}:
                    raise ValueError(
                        "Readwise authentication failed. Check your READWISE_API_TOKEN."
                    ) from exc
                raise ValueError(f"Readwise API request failed with status {status}.") from exc
            except httpx.RequestError as exc:
                raise ValueError(
                    "Could not reach the Readwise API. Check your network connection and try again."
                ) from exc

            payload = response.json()
            for doc in payload.get("results", []):
                items.append(_document_to_source_item(doc))
                if len(items) >= limit:
                    return items

            page_cursor = str(payload.get("nextPageCursor") or "")
            if not page_cursor:
                break
            remaining = limit - len(items)

        return items


def _document_to_source_item(doc: dict[str, Any]) -> SourceItem:
    source_url = str(doc.get("source_url") or doc.get("url") or "")
    title = str(doc.get("title") or source_url)
    source_type = _source_type(str(doc.get("category") or ""), source_url)
    html_content = str(doc.get("html_content") or "")
    summary = str(doc.get("summary") or "")
    notes = str(doc.get("notes") or "")
    raw_text = html_content or summary or notes

    return SourceItem(
        url=source_url,
        title=title,
        source_type=source_type,
        tags=_tags(doc.get("tags")),
        saved_at=_parse_datetime(str(doc.get("saved_at") or doc.get("created_at") or "")),
        inbox_provider=ReadwiseConnector.connector_id,
        external_id=str(doc.get("id") or ""),
        provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
        provider_metadata={
            "reader_url": doc.get("url") or "",
            "category": doc.get("category") or "",
            "location": doc.get("location") or "",
            "site_name": doc.get("site_name") or "",
            "source": doc.get("source") or "",
        },
        pre_extracted_content=PreExtractedSourceContent(
            raw_text=raw_text,
            cleaned_text=summary,
            archived_markdown=html_content,
            raw_capture_kind=_raw_capture_kind(source_type),
            author=str(doc.get("author") or ""),
            published_date=str(doc.get("published_date") or ""),
            word_count=int(doc.get("word_count") or 0),
            extraction_quality=(
                ExtractionQuality.FULL if html_content else ExtractionQuality.PARTIAL
            ),
            extraction_method="readwise_reader_api",
            raw_metadata={"readwise_id": str(doc.get("id") or "")},
            evidence_metadata={"notes": notes, "summary": summary},
        ),
        extra={"raw_document": doc},
    )


def _source_type(category: str, url: str = "") -> SourceType:
    url_type = classify_url(url) if url else SourceType.GENERIC
    if url_type in {SourceType.YOUTUBE, SourceType.X_THREAD, SourceType.PDF}:
        return url_type

    normalized = category.strip().lower()
    if normalized == "video":
        return SourceType.YOUTUBE
    if normalized == "tweet":
        return SourceType.X_THREAD
    if normalized == "pdf":
        return SourceType.PDF
    if normalized in {"article", "email", "rss", "epub", "highlight", "note"}:
        return SourceType.ARTICLE
    return SourceType.GENERIC


def _raw_capture_kind(source_type: SourceType) -> str:
    return {
        SourceType.YOUTUBE: "readwise_video",
        SourceType.X_THREAD: "readwise_thread",
        SourceType.PDF: "readwise_pdf",
        SourceType.ARTICLE: "readwise_article",
        SourceType.GENERIC: "readwise_document",
        SourceType.DERIVED_WORK: "readwise_document",
    }[source_type]


def _tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict):
        tags: list[str] = []
        for key, raw in value.items():
            if isinstance(raw, dict):
                tags.append(str(raw.get("name") or key))
            else:
                tags.append(str(raw or key))
        return [tag for tag in tags if tag.strip()]
    return []


def _parse_datetime(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)

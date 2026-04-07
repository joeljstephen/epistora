from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat(timespec="seconds")


def friendly_date(dt: datetime | None = None) -> str:
    dt = dt or utcnow()
    return dt.strftime("%Y-%m-%d %H:%M UTC")

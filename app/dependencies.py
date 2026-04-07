from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.storage.sqlite import Database


@lru_cache
def get_database() -> Database:
    settings = get_settings()
    db = Database(settings.db_path)
    db.connect()
    return db

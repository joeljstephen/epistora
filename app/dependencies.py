from __future__ import annotations

from fastapi import Request

from app.config import get_settings
from app.storage.sqlite import Database


def create_database() -> Database:
    """Create a connected Database for process-scoped use."""
    settings = get_settings()
    db = Database(settings.db_path)
    db.connect()
    return db


def get_database(request: Request) -> Database:
    """FastAPI dependency backed by the application lifespan connection."""
    return request.app.state.db

"""Dependencies and helpers shared by the API routers."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from sau import storage
from sau.db import session_scope
from sau.models import Asset


def get_session() -> Iterator[Session]:  # pragma: no cover - dependency plumbing
    with session_scope() as session:
        yield session


def register_asset_row(session: Session, storage_key: str) -> Asset:
    """Turn an already-uploaded object into an `Asset`.

    Shared by the one-off upload path and the series one so that both agree on
    what "registered" means. Only the size is read; duration and dimensions
    are filled in by the first transcode, which already has the file locally.
    """
    try:
        size_bytes = storage.size_of(storage_key)
    except Exception as exc:  # any storage failure is a bad key from the caller
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"object not readable: {exc}"
        ) from exc

    asset = Asset(storage_key=storage_key, size_bytes=size_bytes)
    session.add(asset)
    session.flush()
    return asset

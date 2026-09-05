"""Registering and caching per-platform source objects."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from sau import storage
from sau.logging import get_logger
from sau.models import Asset, Platform, Rendition

log = get_logger(__name__)


def rendition_key(asset_id: str, platform: Platform) -> str:
    return f"renditions/{asset_id}/{platform.value}.mp4"


def ensure_rendition(session: Session, asset: Asset, platform: Platform) -> Rendition:
    """Return the platform's source object registration if absent.

    The upload must already satisfy the target platform's video requirements.
    Reusing the R2 object avoids downloading, transcoding, and uploading a
    second copy for every platform.
    """
    existing = session.execute(
        select(Rendition).where(
            Rendition.asset_id == asset.id, Rendition.platform == platform
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    key = asset.storage_key
    rendition = Rendition(
        asset_id=asset.id, platform=platform, storage_key=key, size_bytes=asset.size_bytes
    )
    session.add(rendition)
    session.flush()

    log.info(
        "rendition.registered",
        asset_id=asset.id, platform=platform.value, key=key, bytes=asset.size_bytes,
    )
    return rendition

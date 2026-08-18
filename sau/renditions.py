"""Producing and caching per-platform renditions."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from sau import storage, transcode
from sau.logging import get_logger
from sau.models import Asset, Platform, Rendition

log = get_logger(__name__)


def rendition_key(asset_id: str, platform: Platform) -> str:
    return f"renditions/{asset_id}/{platform.value}.mp4"


def ensure_rendition(session: Session, asset: Asset, platform: Platform) -> Rendition:
    """Return the platform's rendition, transcoding it if absent.

    Renditions are cached in the database and object storage, so retrying a
    failed publish never re-encodes the video.
    """
    existing = session.execute(
        select(Rendition).where(
            Rendition.asset_id == asset.id, Rendition.platform == platform
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    key = rendition_key(asset.id, platform)

    with tempfile.TemporaryDirectory(prefix="sau-") as tmpdir:
        workdir = Path(tmpdir)
        source = storage.download_file(asset.storage_key, workdir / "source.mp4")
        _record_probe(asset, source)
        output = transcode.transcode_for(platform, source, workdir / "out.mp4")
        stored = storage.upload_file(output, key)

    rendition = Rendition(
        asset_id=asset.id, platform=platform, storage_key=stored.key, size_bytes=stored.size_bytes
    )
    session.add(rendition)
    session.flush()

    log.info(
        "rendition.created",
        asset_id=asset.id, platform=platform.value, key=key, bytes=stored.size_bytes,
    )
    return rendition


def _record_probe(asset: Asset, source: Path) -> None:
    """Backfill the asset's technical metadata on first transcode.

    Probing is deferred to here rather than done at registration time so the
    API never has to pull a multi-gigabyte file just to read its header.
    """
    if asset.duration_seconds is not None:
        return
    info = transcode.probe(source)
    asset.duration_seconds = info.duration_seconds
    asset.width = info.width
    asset.height = info.height
    log.info("asset.probed", asset_id=asset.id, duration=info.duration_seconds)

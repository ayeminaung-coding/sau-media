"""Preparing and caching per-platform rendition objects."""

from __future__ import annotations

import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sau import storage
from sau.db import session_scope
from sau.errors import PreparationError
from sau.logging import get_logger
from sau.models import Asset, Platform, Rendition, RenditionState
from sau.transcode import (
    SPECS,
    TRANSCODE_TIMEOUT_SECONDS,
    MediaValidationError,
    RenditionSpec,
    SourceInfo,
    VideoInfo,
    probe,
    profile_identity,
    transcode,
    validate_output,
    validate_source,
)

log = get_logger(__name__)


@dataclass(frozen=True)
class ClaimedRendition:
    source_key: str
    source_size_bytes: int
    profile_identity: str
    state: RenditionState
    storage_key: str
    claim_token: str | None = None


@dataclass(frozen=True)
class PreparedRendition:
    storage_key: str
    size_bytes: int
    profile_identity: str


def _now() -> datetime:
    return datetime.now(UTC)


RENDITION_LEASE = timedelta(seconds=TRANSCODE_TIMEOUT_SECONDS * 2)


def _discard_claim_object(key: str) -> None:
    try:
        storage.delete(key)
    except Exception as exc:
        log.warning("rendition.claim_cleanup_failed", key=key, error=str(exc))


def _profile_key(profile_identity: str) -> str:
    return profile_identity.rsplit(":", 1)[-1]


def rendition_key(asset_id: str, platform: Platform, profile: str = "legacy") -> str:
    return f"renditions/{asset_id}/{platform.value}/{_profile_key(profile)}.mp4"


def ensure_rendition(session: Session, asset: Asset, platform: Platform) -> Rendition:
    existing = session.execute(
        select(Rendition).where(
            Rendition.asset_id == asset.id,
            Rendition.platform == platform,
            Rendition.profile_identity == "legacy",
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    rendition = Rendition(
        asset_id=asset.id,
        platform=platform,
        profile_identity="legacy",
        storage_key=asset.storage_key,
        size_bytes=asset.size_bytes,
        state=RenditionState.LEGACY_SOURCE,
    )
    session.add(rendition)
    session.flush()
    log.info(
        "rendition.legacy_registered",
        asset_id=asset.id,
        platform=platform.value,
        key=asset.storage_key,
        bytes=asset.size_bytes,
    )
    return rendition


def _claim_preparation(asset_id: str, platform: Platform) -> ClaimedRendition:
    with session_scope() as session:
        asset = session.get(Asset, asset_id)
        if asset is None:
            raise PreparationError(
                f"asset {asset_id} does not exist", code="asset_not_found", retryable=False
            )
        now = _now()
        profile = profile_identity(platform, SPECS[platform])
        rendition = session.execute(
            select(Rendition)
            .where(
                Rendition.asset_id == asset_id,
                Rendition.platform == platform,
                Rendition.profile_identity == profile,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if rendition is not None and rendition.state is RenditionState.READY:
            return ClaimedRendition(
                source_key=asset.storage_key,
                source_size_bytes=asset.size_bytes,
                profile_identity=profile,
                state=rendition.state,
                storage_key=rendition.storage_key,
            )
        if (
            rendition is not None
            and rendition.state is RenditionState.PROCESSING
            and rendition.lease_expires_at is not None
            and rendition.lease_expires_at > now
        ):
            raise PreparationError(
                f"rendition preparation is already running for {asset_id} on {platform.value}",
                code="rendition_in_progress",
            )

        claim_token = str(uuid.uuid4())
        claim_key = rendition_key(asset_id, platform, f"{profile}:{claim_token}")
        if rendition is None:
            try:
                with session.begin_nested():
                    rendition = Rendition(
                        asset_id=asset_id,
                        platform=platform,
                        profile_identity=profile,
                        storage_key=claim_key,
                        size_bytes=0,
                        state=RenditionState.PENDING,
                    )
                    session.add(rendition)
                    session.flush()
            except IntegrityError as exc:
                rendition = session.execute(
                    select(Rendition)
                    .where(
                        Rendition.asset_id == asset_id,
                        Rendition.platform == platform,
                        Rendition.profile_identity == profile,
                    )
                    .with_for_update()
                ).scalar_one_or_none()
                if rendition is None:
                    raise PreparationError(
                        f"rendition claim raced for {asset_id} on {platform.value}",
                        code="rendition_claim_race",
                    ) from exc
                if rendition.state is RenditionState.READY:
                    return ClaimedRendition(
                        source_key=asset.storage_key,
                        source_size_bytes=asset.size_bytes,
                        profile_identity=profile,
                        state=rendition.state,
                        storage_key=rendition.storage_key,
                    )
                if (
                    rendition.state is RenditionState.PROCESSING
                    and rendition.lease_expires_at is not None
                    and rendition.lease_expires_at > now
                ):
                    raise PreparationError(
                        f"rendition preparation is already running for {asset_id} on "
                        f"{platform.value}",
                        code="rendition_in_progress",
                    ) from exc
        rendition.state = RenditionState.PROCESSING
        rendition.claim_token = claim_token
        rendition.lease_expires_at = now + RENDITION_LEASE
        rendition.storage_key = claim_key
        rendition.error = None
        rendition.started_at = now
        rendition.completed_at = None
        session.flush()
        return ClaimedRendition(
            source_key=asset.storage_key,
            source_size_bytes=asset.size_bytes,
            profile_identity=profile,
            state=rendition.state,
            storage_key=claim_key,
            claim_token=claim_token,
        )


def _mark_failed(
    asset_id: str, platform: Platform, profile: str, claim_token: str, message: str
) -> None:
    with session_scope() as session:
        result = cast(
            CursorResult[Any],
            session.execute(
                update(Rendition)
                .where(
                    Rendition.asset_id == asset_id,
                    Rendition.platform == platform,
                    Rendition.profile_identity == profile,
                    Rendition.claim_token == claim_token,
                    Rendition.state == RenditionState.PROCESSING,
                    Rendition.lease_expires_at > _now(),
                )
                .values(
                    state=RenditionState.FAILED,
                    error=message[:2000],
                    claim_token=None,
                    lease_expires_at=None,
                    completed_at=_now(),
                )
            ),
        )
        if result.rowcount != 1:
            log.warning(
                "rendition.stale_failure_ignored",
                asset_id=asset_id,
                platform=platform.value,
                profile=profile,
            )
            return
        log.error(
            "rendition.preparation_failed",
            asset_id=asset_id,
            platform=platform.value,
            profile=profile,
            error=message,
        )


def _mark_ready(
    asset_id: str,
    platform: Platform,
    profile: str,
    claim_token: str,
    storage_key: str,
    size_bytes: int,
    source_info: SourceInfo,
    output_info: VideoInfo,
) -> None:
    with session_scope() as session:
        result = cast(
            CursorResult[Any],
            session.execute(
                update(Rendition)
                .where(
                    Rendition.asset_id == asset_id,
                    Rendition.platform == platform,
                    Rendition.profile_identity == profile,
                    Rendition.claim_token == claim_token,
                    Rendition.state == RenditionState.PROCESSING,
                    Rendition.lease_expires_at > _now(),
                )
                .values(
                    storage_key=storage_key,
                    size_bytes=size_bytes,
                    state=RenditionState.READY,
                    error=None,
                    claim_token=None,
                    lease_expires_at=None,
                    duration_seconds=output_info.duration_seconds,
                    width=output_info.width,
                    height=output_info.height,
                    video_codec=output_info.video_codec,
                    audio_codec=output_info.audio_codec,
                    completed_at=_now(),
                )
            ),
        )
        if result.rowcount != 1:
            raise PreparationError(
                f"rendition claim expired for {asset_id} on {platform.value}",
                code="stale_rendition_claim",
                retryable=True,
            )
        asset = session.get(Asset, asset_id)
        if asset is not None:
            asset.duration_seconds = source_info.duration_seconds
            asset.width = source_info.width
            asset.height = source_info.height
        log.info(
            "rendition.prepared",
            asset_id=asset_id,
            platform=platform.value,
            profile=profile,
            key=storage_key,
            bytes=size_bytes,
        )


def prepare_rendition(asset_id: str, platform: Platform) -> PreparedRendition:
    claim = _claim_preparation(asset_id, platform)
    if claim.state is RenditionState.READY:
        with session_scope() as session:
            rendition = session.execute(
                select(Rendition).where(
                    Rendition.asset_id == asset_id,
                    Rendition.platform == platform,
                    Rendition.profile_identity == claim.profile_identity,
                )
            ).scalar_one()
            return PreparedRendition(
                storage_key=rendition.storage_key,
                size_bytes=rendition.size_bytes,
                profile_identity=claim.profile_identity,
            )
    claim_token = claim.claim_token
    if claim_token is None:
        raise PreparationError(
            f"rendition claim was not created for {asset_id} on {platform.value}",
            code="missing_claim_token",
            retryable=True,
        )

    spec: RenditionSpec = SPECS[platform]
    try:
        if (
            spec.max_source_size_bytes is not None
            and claim.source_size_bytes > spec.max_source_size_bytes
        ):
            raise MediaValidationError(
                "source_too_large", "source exceeds the profile size limit"
            )
        with tempfile.TemporaryDirectory(prefix="sau-rendition-") as temporary:
            source_path = Path(temporary) / "source"
            output_path = Path(temporary) / "output.mp4"
            storage.download_file(claim.source_key, source_path)
            source_video = probe(source_path)
            source_info = SourceInfo(
                duration_seconds=source_video.duration_seconds,
                width=source_video.width,
                height=source_video.height,
                size_bytes=source_path.stat().st_size,
                container=source_video.container,
                video_codec=source_video.video_codec,
                audio_codec=source_video.audio_codec,
            )
            validate_source(source_info, spec)
            transcode(source_path, output_path, spec)
            output_info = probe(output_path)
            validate_output(output_info, spec)
            stored = storage.upload_file(output_path, claim.storage_key)
            _mark_ready(
                asset_id,
                platform,
                claim.profile_identity,
                claim_token,
                stored.key,
                stored.size_bytes,
                source_info,
                output_info,
            )
            return PreparedRendition(
                storage_key=stored.key,
                size_bytes=stored.size_bytes,
                profile_identity=claim.profile_identity,
            )
    except PreparationError:
        _discard_claim_object(claim.storage_key)
        raise
    except MediaValidationError as exc:
        _discard_claim_object(claim.storage_key)
        _mark_failed(
            asset_id, platform, claim.profile_identity, claim_token, str(exc)
        )
        raise PreparationError(str(exc), code=exc.code, retryable=False) from exc
    except Exception as exc:
        _discard_claim_object(claim.storage_key)
        _mark_failed(
            asset_id, platform, claim.profile_identity, claim_token, str(exc)
        )
        raise PreparationError(
            f"media preparation failed for {asset_id} on {platform.value}",
            code="media_preparation_failed",
        ) from exc

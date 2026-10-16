"""Media preparation orchestration."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sau import renditions, storage
from sau.errors import PreparationError
from sau.models import Asset, Base, Platform, Rendition, RenditionState
from sau.transcode import (
    MEDIA_SIZE_LIMIT_BYTES,
    SPECS,
    TranscodeError,
    VideoInfo,
    profile_identity,
)


def _profile() -> str:
    return "tiktok:1:profile"


def test_prepare_rendition_uploads_verified_output(monkeypatch):
    calls = []

    def fake_claim(asset_id, platform):
        calls.append(("claim", asset_id, platform))
        return renditions.ClaimedRendition(
            source_key="sources/asset.mp4",
            source_size_bytes=6,
            profile_identity=_profile(),
            state=RenditionState.PROCESSING,
            storage_key="renditions/asset-1/tiktok/claim-1.mp4",
            claim_token="claim-1",
        )

    def fake_download(key, local_path):
        calls.append(("download", key, local_path))
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(b"source")

    def fake_probe(path):
        if path.name == "source":
            return VideoInfo(
                duration_seconds=30,
                width=1080,
                height=1920,
                size_bytes=6,
                container="mov,mp4",
                video_codec="h264",
                audio_codec="aac",
                frame_rate=30,
                pixel_format="yuv420p",
                video_profile="High",
            )
        return VideoInfo(
            duration_seconds=30,
            width=1080,
            height=1920,
            size_bytes=8,
            container="mp4",
            video_codec="h264",
            audio_codec="aac",
            frame_rate=30,
            pixel_format="yuv420p",
            video_profile="High",
        )

    def fake_transcode(source, destination, spec):
        calls.append(("transcode", source, destination, spec))
        destination.write_bytes(b"prepared")

    def fake_upload(local_path, key):
        calls.append(("upload", local_path, key))
        return storage.StoredObject(key=key, size_bytes=local_path.stat().st_size)

    def fake_ready(*args):
        calls.append(("ready", *args))

    monkeypatch.setattr(renditions, "_claim_preparation", fake_claim)
    monkeypatch.setattr(renditions.storage, "download_file", fake_download)
    monkeypatch.setattr(renditions, "probe", fake_probe)
    monkeypatch.setattr(renditions, "transcode", fake_transcode)
    monkeypatch.setattr(renditions.storage, "upload_file", fake_upload)
    monkeypatch.setattr(renditions, "_mark_ready", fake_ready)

    result = renditions.prepare_rendition("asset-1", Platform.TIKTOK)

    assert result.storage_key.endswith("claim-1.mp4")
    assert result.size_bytes == len(b"prepared")
    ready_call = next(call for call in calls if call[0] == "ready")
    assert ready_call[-2].duration_seconds == 30
    assert ready_call[-1].width == 1080
    assert [call[0] for call in calls] == [
        "claim",
        "download",
        "transcode",
        "upload",
        "ready",
    ]


def test_oversized_claimed_source_is_rejected_before_download(monkeypatch):
    def fake_claim(asset_id, platform):
        return renditions.ClaimedRendition(
            source_key="sources/large.mp4",
            source_size_bytes=MEDIA_SIZE_LIMIT_BYTES + 1,
            profile_identity=_profile(),
            state=RenditionState.PROCESSING,
            storage_key="renditions/asset-1/tiktok/claim-1.mp4",
            claim_token="claim-1",
        )

    def fake_download(*args, **kwargs):
        pytest.fail("oversized source must be rejected before download")

    def fake_failed(*args):
        assert args[0] == "asset-1"

    monkeypatch.setattr(renditions, "_claim_preparation", fake_claim)
    monkeypatch.setattr(renditions.storage, "download_file", fake_download)
    monkeypatch.setattr(renditions, "_mark_failed", fake_failed)
    monkeypatch.setattr(renditions, "_discard_claim_object", lambda key: None)

    with pytest.raises(PreparationError) as error:
        renditions.prepare_rendition("asset-1", Platform.TIKTOK)

    assert error.value.code == "source_too_large"


def test_prepare_rendition_marks_invalid_source_and_cleans_temp_files(monkeypatch):
    temporary_paths = []

    def fake_claim(asset_id, platform):
        return renditions.ClaimedRendition(
            source_key="sources/asset.mp4",
            source_size_bytes=6,
            profile_identity=_profile(),
            state=RenditionState.PROCESSING,
            storage_key="renditions/asset-1/tiktok/claim-1.mp4",
            claim_token="claim-1",
        )

    def fake_download(key, local_path):
        temporary_paths.append(local_path.parent)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(b"source")

    def fake_probe(path):
        return VideoInfo(duration_seconds=601, width=1080, height=1920)

    def fake_transcode(source, destination, spec):
        pytest.fail("transcode should not run for an invalid source")

    def fake_failed(*args):
        assert args[0] == "asset-1"
        assert args[1] is Platform.TIKTOK

    monkeypatch.setattr(renditions, "_claim_preparation", fake_claim)
    monkeypatch.setattr(renditions.storage, "download_file", fake_download)
    monkeypatch.setattr(renditions, "probe", fake_probe)
    monkeypatch.setattr(renditions, "transcode", fake_transcode)
    monkeypatch.setattr(renditions, "_mark_failed", fake_failed)
    monkeypatch.setattr(renditions, "_discard_claim_object", lambda key: None)

    with pytest.raises(PreparationError) as error:
        renditions.prepare_rendition("asset-1", Platform.TIKTOK)

    assert error.value.code == "duration_exceeds_limit"
    assert all(not path.exists() for path in temporary_paths)


def test_prepare_rendition_marks_transcode_failure_and_cleans_temp_files(monkeypatch):
    temporary_paths = []

    def fake_claim(asset_id, platform):
        return renditions.ClaimedRendition(
            source_key="sources/asset.mp4",
            source_size_bytes=6,
            profile_identity=_profile(),
            state=RenditionState.PROCESSING,
            storage_key="renditions/asset-1/tiktok/claim-1.mp4",
            claim_token="claim-1",
        )

    def fake_download(key, local_path):
        temporary_paths.append(local_path.parent)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(b"source")

    def fake_probe(path):
        return VideoInfo(
            duration_seconds=30,
            width=1080,
            height=1920,
            size_bytes=6,
            container="mov,mp4",
            video_codec="h264",
            audio_codec="aac",
        )

    def fake_transcode(source, destination, spec):
        raise TranscodeError("ffmpeg failed")

    def fake_failed(*args):
        assert args[0] == "asset-1"

    monkeypatch.setattr(renditions, "_claim_preparation", fake_claim)
    monkeypatch.setattr(renditions.storage, "download_file", fake_download)
    monkeypatch.setattr(renditions, "probe", fake_probe)
    monkeypatch.setattr(renditions, "transcode", fake_transcode)
    monkeypatch.setattr(renditions, "_mark_failed", fake_failed)
    monkeypatch.setattr(renditions, "_discard_claim_object", lambda key: None)

    with pytest.raises(PreparationError) as error:
        renditions.prepare_rendition("asset-1", Platform.TIKTOK)

    assert error.value.code == "media_preparation_failed"
    assert all(not path.exists() for path in temporary_paths)


def _patch_session_scope(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def scope():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(renditions, "session_scope", scope)
    with session_factory() as session:
        asset = Asset(storage_key="sources/asset.mp4", size_bytes=6)
        session.add(asset)
        session.commit()
        asset_id = asset.id
    return session_factory, asset_id


def _profile_for(platform: Platform) -> str:
    return profile_identity(platform, SPECS[platform])


def test_ready_rendition_is_reused_without_media_work(monkeypatch):
    session_factory, asset_id = _patch_session_scope(monkeypatch)
    profile = _profile_for(Platform.TIKTOK)
    with session_factory() as session:
        session.add(
            Rendition(
                asset_id=asset_id,
                platform=Platform.TIKTOK,
                profile_identity=profile,
                storage_key="renditions/asset-1/tiktok/ready.mp4",
                size_bytes=42,
                state=RenditionState.READY,
            )
        )

    def fail_download(*args, **kwargs):
        pytest.fail("ready renditions must not be downloaded again")

    monkeypatch.setattr(renditions.storage, "download_file", fail_download)
    result = renditions.prepare_rendition(asset_id, Platform.TIKTOK)

    assert result.storage_key.endswith("ready.mp4")
    assert result.size_bytes == 42


def test_active_lease_blocks_a_second_claim(monkeypatch):
    session_factory, asset_id = _patch_session_scope(monkeypatch)
    profile = _profile_for(Platform.TIKTOK)
    with session_factory() as session:
        session.add(
            Rendition(
                asset_id=asset_id,
                platform=Platform.TIKTOK,
                profile_identity=profile,
                storage_key="renditions/asset-1/tiktok/active.mp4",
                size_bytes=0,
                state=RenditionState.PROCESSING,
                claim_token="active",
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )

    with pytest.raises(PreparationError) as error:
        renditions._claim_preparation(asset_id, Platform.TIKTOK)
    assert error.value.code == "rendition_in_progress"


def test_expired_lease_can_be_reclaimed(monkeypatch):
    session_factory, asset_id = _patch_session_scope(monkeypatch)
    profile = _profile_for(Platform.TIKTOK)
    with session_factory() as session:
        session.add(
            Rendition(
                asset_id=asset_id,
                platform=Platform.TIKTOK,
                profile_identity=profile,
                storage_key="renditions/asset-1/tiktok/expired.mp4",
                size_bytes=0,
                state=RenditionState.PROCESSING,
                claim_token="expired",
                lease_expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )

    claim = renditions._claim_preparation(asset_id, Platform.TIKTOK)

    assert claim.state is RenditionState.PROCESSING
    assert claim.claim_token not in (None, "expired")


def test_stale_token_cannot_finalize_a_rendition(monkeypatch):
    session_factory, asset_id = _patch_session_scope(monkeypatch)
    profile = _profile_for(Platform.TIKTOK)
    with session_factory() as session:
        session.add(
            Rendition(
                asset_id=asset_id,
                platform=Platform.TIKTOK,
                profile_identity=profile,
                storage_key="renditions/asset-1/tiktok/claimed.mp4",
                size_bytes=0,
                state=RenditionState.PROCESSING,
                claim_token="current",
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )

    source = renditions.SourceInfo(duration_seconds=30, width=1080, height=1920, size_bytes=6)
    output = VideoInfo(
        duration_seconds=30,
        width=1080,
        height=1920,
        size_bytes=42,
        container="mp4",
        video_codec="h264",
        audio_codec="aac",
        frame_rate=30,
        pixel_format="yuv420p",
        video_profile="High",
    )
    with pytest.raises(PreparationError) as error:
        renditions._mark_ready(
            asset_id,
            Platform.TIKTOK,
            profile,
            "stale",
            "renditions/asset-1/tiktok/stale.mp4",
            42,
            source,
            output,
        )
    assert error.value.code == "stale_rendition_claim"

    renditions._mark_failed(asset_id, Platform.TIKTOK, profile, "stale", "failed")
    with session_factory() as session:
        rendition = session.query(Rendition).one()
        assert rendition.state is RenditionState.PROCESSING
        assert rendition.claim_token == "current"

"""Rendition specs and the ffmpeg filter string."""

import json
import subprocess

import pytest

from sau import transcode
from sau.models import Platform
from sau.transcode import (
    SPECS,
    DurationPolicy,
    MediaValidationError,
    RenditionSpec,
    SourceInfo,
    TranscodeError,
    _scale_filter,
    profile_identity,
    validate_output,
    validate_source,
)


def test_every_platform_has_a_spec():
    assert set(SPECS) == set(Platform)


def test_vertical_targets_are_nine_by_sixteen():
    for platform in (Platform.TIKTOK, Platform.FACEBOOK_REEL):
        spec = SPECS[platform]
        assert spec.width * 16 == spec.height * 9


def test_reels_have_the_platform_duration_limit():
    assert SPECS[Platform.FACEBOOK_REEL].max_duration_seconds == 90


def test_padded_specs_letterbox_to_exact_dimensions():
    chain = _scale_filter(SPECS[Platform.TIKTOK])
    assert "force_original_aspect_ratio=decrease" in chain
    assert "pad=1080:1920" in chain


def test_unpadded_specs_keep_aspect_and_force_even_dimensions():
    chain = _scale_filter(SPECS[Platform.FACEBOOK_VIDEO])
    assert "pad=" not in chain
    # libx264 rejects odd dimensions after a decrease-fit scale.
    assert "trunc(iw/2)*2" in chain


def test_profile_identity_is_stable_and_platform_specific():
    identity = profile_identity(Platform.TIKTOK, SPECS[Platform.TIKTOK])
    assert identity == profile_identity(Platform.TIKTOK, SPECS[Platform.TIKTOK])
    assert identity != profile_identity(Platform.FACEBOOK_REEL, SPECS[Platform.TIKTOK])


def test_profile_identity_changes_when_profile_changes():
    spec = SPECS[Platform.TIKTOK]
    changed = RenditionSpec(
        width=spec.width,
        height=spec.height,
        video_bitrate=spec.video_bitrate,
        profile_version=spec.profile_version + 1,
    )
    assert profile_identity(Platform.TIKTOK, spec) != profile_identity(
        Platform.TIKTOK, changed
    )
    codec_changed = RenditionSpec(
        width=spec.width,
        height=spec.height,
        video_bitrate=spec.video_bitrate,
        video_codec="libx265",
    )
    assert profile_identity(Platform.TIKTOK, spec) != profile_identity(
        Platform.TIKTOK, codec_changed
    )


def test_valid_source_passes_profile_validation():
    source = SourceInfo(
        duration_seconds=30,
        width=1080,
        height=1920,
        size_bytes=1024,
        container="mov,mp4",
        video_codec="h264",
        audio_codec="aac",
    )
    validate_source(source, SPECS[Platform.FACEBOOK_REEL])


def test_overlong_source_fails_by_default():
    source = SourceInfo(duration_seconds=91, width=1080, height=1920, size_bytes=1024)
    with pytest.raises(MediaValidationError) as error:
        validate_source(source, SPECS[Platform.FACEBOOK_REEL])
    assert error.value.code == "duration_exceeds_limit"


def test_trim_policy_allows_overlong_source():
    spec = RenditionSpec(
        width=1080,
        height=1920,
        video_bitrate="6M",
        max_duration_seconds=90,
        duration_policy=DurationPolicy.TRIM,
    )
    source = SourceInfo(duration_seconds=91, width=1080, height=1920, size_bytes=1024)
    validate_source(source, spec)


def test_source_size_limit_is_enforced():
    spec = RenditionSpec(
        width=1080,
        height=1920,
        video_bitrate="6M",
        max_source_size_bytes=100,
    )
    source = SourceInfo(duration_seconds=30, width=1080, height=1920, size_bytes=101)
    with pytest.raises(MediaValidationError) as error:
        validate_source(source, spec)
    assert error.value.code == "source_too_large"


def test_optional_media_requirements_are_checked():
    spec = RenditionSpec(
        width=1080,
        height=1920,
        video_bitrate="6M",
        accepted_containers=("mp4",),
        accepted_video_codecs=("h264",),
        accepted_audio_codecs=("aac",),
    )
    source = SourceInfo(
        duration_seconds=30,
        width=1080,
        height=1920,
        size_bytes=1024,
        container="webm",
        video_codec="vp9",
        audio_codec="opus",
    )
    with pytest.raises(MediaValidationError) as error:
        validate_source(source, spec)
    assert error.value.code == "unsupported_container"


def test_invalid_dimensions_are_rejected():
    source = SourceInfo(duration_seconds=30, width=0, height=1920, size_bytes=1024)
    with pytest.raises(MediaValidationError) as error:
        validate_source(source, SPECS[Platform.FACEBOOK_REEL])
    assert error.value.code == "invalid_dimensions"


def test_output_dimensions_are_verified():
    output = transcode.VideoInfo(
        duration_seconds=30,
        width=720,
        height=1280,
        size_bytes=1024,
        container="mp4",
        video_codec="h264",
        audio_codec="aac",
        frame_rate=30,
        pixel_format="yuv420p",
        video_profile="High",
    )
    with pytest.raises(MediaValidationError) as error:
        validate_output(output, SPECS[Platform.FACEBOOK_REEL])
    assert error.value.code == "output_dimensions_mismatch"


def test_output_duration_cap_is_verified():
    output = transcode.VideoInfo(
        duration_seconds=91,
        width=1080,
        height=1920,
        size_bytes=1024,
        container="mp4",
        video_codec="h264",
        audio_codec="aac",
        frame_rate=30,
        pixel_format="yuv420p",
        video_profile="High",
    )
    with pytest.raises(MediaValidationError) as error:
        validate_output(output, SPECS[Platform.FACEBOOK_REEL])
    assert error.value.code == "output_duration_exceeds_limit"


def test_container_aliases_are_supported():
    spec = RenditionSpec(
        width=1080,
        height=1920,
        video_bitrate="6M",
        accepted_containers=("mp4",),
    )
    source = SourceInfo(
        duration_seconds=30,
        width=1080,
        height=1920,
        size_bytes=1024,
        container="mov,mp4,m4a,3gp,3g2,mj2",
    )
    validate_source(source, spec)


def test_probe_reads_stream_metadata(monkeypatch, tmp_path):
    path = tmp_path / "input.mp4"
    path.write_bytes(b"source")
    result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps(
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "profile": "High",
                        "pix_fmt": "yuv420p",
                        "width": 1080,
                        "height": 1920,
                        "r_frame_rate": "30000/1001",
                    },
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": "30.0", "format_name": "mov,mp4,m4a"},
            }
        ),
        stderr="",
    )
    monkeypatch.setattr(transcode, "ensure_ffmpeg", lambda: None)
    monkeypatch.setattr(transcode.subprocess, "run", lambda *args, **kwargs: result)

    info = transcode.probe(path)

    assert info.container == "mov,mp4,m4a"
    assert info.video_codec == "h264"
    assert info.audio_codec == "aac"
    assert info.frame_rate == pytest.approx(29.97002997)
    assert info.pixel_format == "yuv420p"
    assert info.video_profile == "High"


def test_probe_timeout_is_reported(monkeypatch, tmp_path):
    path = tmp_path / "input.mp4"
    path.write_bytes(b"source")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(transcode, "ensure_ffmpeg", lambda: None)
    monkeypatch.setattr(transcode.subprocess, "run", timeout)

    with pytest.raises(TranscodeError, match="timed out"):
        transcode.probe(path)


def test_transcode_timeout_is_reported(monkeypatch, tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"source")
    destination = tmp_path / "output.mp4"

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(transcode, "ensure_ffmpeg", lambda: None)
    monkeypatch.setattr(transcode.subprocess, "run", timeout)

    with pytest.raises(TranscodeError, match="timed out"):
        transcode.transcode(source, destination, SPECS[Platform.TIKTOK])

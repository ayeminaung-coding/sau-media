"""ffmpeg/ffprobe wrappers producing per-platform renditions.

Each platform gets its own encode rather than a shared "good enough" file:
TikTok and Reels want vertical 9:16, a Facebook feed video keeps its native
aspect. Encoding once per platform costs CPU but avoids the platform doing a
worse job re-encoding for us.
"""

from __future__ import annotations

import enum
import hashlib
import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sau.logging import get_logger
from sau.models import Platform

log = get_logger(__name__)

PROBE_TIMEOUT_SECONDS = 60
TRANSCODE_TIMEOUT_SECONDS = 3600
MEDIA_SIZE_LIMIT_BYTES = 8 * 1024**3


class TranscodeError(RuntimeError):
    """ffmpeg or ffprobe exited non-zero."""


class MediaValidationError(ValueError):
    """A source cannot satisfy a platform profile."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class DurationPolicy(enum.StrEnum):
    FAIL = "fail"
    TRIM = "trim"


@dataclass(frozen=True)
class VideoInfo:
    duration_seconds: float
    width: int
    height: int
    size_bytes: int = 0
    container: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    frame_rate: float | None = None
    pixel_format: str | None = None
    video_profile: str | None = None


@dataclass(frozen=True)
class SourceInfo:
    duration_seconds: float
    width: int
    height: int
    size_bytes: int
    container: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None


@dataclass(frozen=True)
class RenditionSpec:
    """Target encode parameters for one platform."""

    width: int
    height: int
    video_bitrate: str
    video_codec: str = "libx264"
    video_profile: str = "high"
    pixel_format: str = "yuv420p"
    audio_codec: str = "aac"
    audio_sample_rate: int = 44100
    muxer: str = "mp4"
    audio_bitrate: str = "128k"
    fps: int = 30
    #: Hard trim, in seconds. `None` keeps the full duration.
    max_duration_seconds: int | None = None
    #: Letterbox/pillarbox to exactly width x height when True; otherwise the
    #: source aspect is preserved and only downscaled to fit.
    pad_to_fit: bool = True
    profile_version: int = 1
    duration_policy: DurationPolicy = DurationPolicy.FAIL
    max_source_size_bytes: int | None = MEDIA_SIZE_LIMIT_BYTES
    max_output_size_bytes: int | None = MEDIA_SIZE_LIMIT_BYTES
    accepted_containers: tuple[str, ...] = ()
    accepted_video_codecs: tuple[str, ...] = ()
    accepted_audio_codecs: tuple[str, ...] = ()
    require_audio: bool = False

    @property
    def profile_hash(self) -> str:
        payload = {
            "accepted_audio_codecs": sorted(self.accepted_audio_codecs),
            "accepted_containers": sorted(self.accepted_containers),
            "accepted_video_codecs": sorted(self.accepted_video_codecs),
            "audio_bitrate": self.audio_bitrate,
            "audio_codec": self.audio_codec,
            "audio_sample_rate": self.audio_sample_rate,
            "duration_policy": self.duration_policy.value,
            "fps": self.fps,
            "height": self.height,
            "max_duration_seconds": self.max_duration_seconds,
            "max_output_size_bytes": self.max_output_size_bytes,
            "max_source_size_bytes": self.max_source_size_bytes,
            "muxer": self.muxer,
            "pad_to_fit": self.pad_to_fit,
            "pixel_format": self.pixel_format,
            "profile_version": self.profile_version,
            "require_audio": self.require_audio,
            "video_bitrate": self.video_bitrate,
            "video_codec": self.video_codec,
            "video_profile": self.video_profile,
            "width": self.width,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


#: Conservative targets. Both platforms re-encode on ingest anyway, so the
#: goal is a clean, spec-compliant master rather than a maximum-quality one.
SOURCE_CONTAINERS = ("mov", "mp4", "matroska", "webm")
SOURCE_VIDEO_CODECS = ("h264", "hevc", "vp8", "vp9", "av1")
SOURCE_AUDIO_CODECS = ("aac", "mp3", "opus", "vorbis")

SPECS: dict[Platform, RenditionSpec] = {
    Platform.TIKTOK: RenditionSpec(
        width=1080,
        height=1920,
        video_bitrate="6M",
        max_duration_seconds=600,
        accepted_containers=SOURCE_CONTAINERS,
        accepted_video_codecs=SOURCE_VIDEO_CODECS,
        accepted_audio_codecs=SOURCE_AUDIO_CODECS,
    ),
    Platform.FACEBOOK_REEL: RenditionSpec(
        width=1080,
        height=1920,
        video_bitrate="6M",
        max_duration_seconds=90,
        accepted_containers=SOURCE_CONTAINERS,
        accepted_video_codecs=SOURCE_VIDEO_CODECS,
        accepted_audio_codecs=SOURCE_AUDIO_CODECS,
    ),
    Platform.FACEBOOK_VIDEO: RenditionSpec(
        width=1920,
        height=1080,
        video_bitrate="8M",
        pad_to_fit=False,
        accepted_containers=SOURCE_CONTAINERS,
        accepted_video_codecs=SOURCE_VIDEO_CODECS,
        accepted_audio_codecs=SOURCE_AUDIO_CODECS,
    ),
}


def profile_identity(platform: Platform, spec: RenditionSpec) -> str:
    return f"{platform.value}:{spec.profile_version}:{spec.profile_hash}"


def _matches_allowed(value: str | None, allowed: tuple[str, ...]) -> bool:
    if value is None:
        return False
    values = {part.strip().lower() for part in value.split(",")}
    return bool(values & {item.lower() for item in allowed})


def validate_source(source: SourceInfo, spec: RenditionSpec) -> None:
    if not math.isfinite(source.duration_seconds) or source.duration_seconds <= 0:
        raise MediaValidationError("invalid_duration", "source duration must be positive")
    if source.width <= 0 or source.height <= 0:
        raise MediaValidationError(
            "invalid_dimensions", "source dimensions must be positive"
        )
    if source.size_bytes <= 0:
        raise MediaValidationError("invalid_size", "source size must be positive")
    if spec.max_source_size_bytes is not None and source.size_bytes > spec.max_source_size_bytes:
        raise MediaValidationError("source_too_large", "source exceeds the profile size limit")
    if (
        spec.max_duration_seconds is not None
        and source.duration_seconds > spec.max_duration_seconds
        and spec.duration_policy is DurationPolicy.FAIL
    ):
        raise MediaValidationError(
            "duration_exceeds_limit", "source duration exceeds the profile limit"
        )
    if spec.accepted_containers and not _matches_allowed(
        source.container, spec.accepted_containers
    ):
        raise MediaValidationError("unsupported_container", "source container is not supported")
    if spec.accepted_video_codecs and not _matches_allowed(
        source.video_codec, spec.accepted_video_codecs
    ):
        raise MediaValidationError(
            "unsupported_video_codec", "source video codec is not supported"
        )
    if spec.require_audio and source.audio_codec is None:
        raise MediaValidationError("missing_audio", "source audio is required")
    if (
        spec.accepted_audio_codecs
        and source.audio_codec is not None
        and not _matches_allowed(source.audio_codec, spec.accepted_audio_codecs)
    ):
        raise MediaValidationError(
            "unsupported_audio_codec", "source audio codec is not supported"
        )


_ENCODER_CODEC_NAMES = {"libx264": "h264", "libx265": "hevc"}


def _codec_matches(actual: str | None, configured: str) -> bool:
    if actual is None:
        return False
    expected = _ENCODER_CODEC_NAMES.get(configured.lower(), configured.lower())
    return actual.lower() == expected


def validate_output(output: VideoInfo, spec: RenditionSpec) -> None:
    if not math.isfinite(output.duration_seconds) or output.duration_seconds <= 0:
        raise MediaValidationError("invalid_output_duration", "output duration must be positive")
    if output.width <= 0 or output.height <= 0:
        raise MediaValidationError(
            "invalid_output_dimensions", "output dimensions must be positive"
        )
    if spec.pad_to_fit and (output.width != spec.width or output.height != spec.height):
        raise MediaValidationError(
            "output_dimensions_mismatch", "output dimensions do not match the profile"
        )
    if not spec.pad_to_fit and (output.width > spec.width or output.height > spec.height):
        raise MediaValidationError(
            "output_dimensions_too_large", "output exceeds the profile dimensions"
        )
    if (
        spec.max_duration_seconds is not None
        and output.duration_seconds > spec.max_duration_seconds + 0.5
    ):
        raise MediaValidationError(
            "output_duration_exceeds_limit", "output duration exceeds the profile limit"
        )
    if output.size_bytes <= 0:
        raise MediaValidationError("invalid_output_size", "output size must be positive")
    if not _codec_matches(output.video_codec, spec.video_codec):
        raise MediaValidationError("output_video_codec_mismatch", "output video codec is not ready")
    if output.pixel_format is None or output.pixel_format.lower() != spec.pixel_format.lower():
        raise MediaValidationError(
            "output_pixel_format_mismatch", "output pixel format is not ready"
        )
    if output.video_profile is None or output.video_profile.lower() != spec.video_profile.lower():
        raise MediaValidationError(
            "output_video_profile_mismatch", "output video profile is not ready"
        )
    if output.frame_rate is None or abs(output.frame_rate - spec.fps) > max(0.1, spec.fps * 0.02):
        raise MediaValidationError("output_frame_rate_mismatch", "output frame rate is not ready")
    if not _matches_allowed(output.container, (spec.muxer,)):
        raise MediaValidationError("output_container_mismatch", "output container is not ready")
    if output.audio_codec is not None and output.audio_codec.lower() != spec.audio_codec.lower():
        raise MediaValidationError("output_audio_codec_mismatch", "output audio codec is not ready")
    if spec.require_audio and output.audio_codec is None:
        raise MediaValidationError("missing_output_audio", "output audio is required")
    if spec.max_output_size_bytes is not None and output.size_bytes > spec.max_output_size_bytes:
        raise MediaValidationError(
            "output_too_large", "output exceeds the profile size limit"
        )


def ensure_ffmpeg() -> None:
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            raise TranscodeError(f"{binary} not found on PATH")


def _parse_frame_rate(value: str | None) -> float | None:
    if value is None or "/" not in value:
        return None
    numerator, denominator = value.split("/", 1)
    try:
        denominator_value = float(denominator)
        if denominator_value == 0:
            return None
        return float(numerator) / denominator_value
    except ValueError:
        return None


def probe(path: Path) -> VideoInfo:
    """Read duration, dimensions, and stream metadata from a media file."""
    ensure_ffmpeg()
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries",
                "stream=codec_type,codec_name,profile,pix_fmt,width,height,r_frame_rate:"
                "format=duration,format_name",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise TranscodeError("ffprobe timed out") from exc
    if result.returncode != 0:
        raise TranscodeError(f"ffprobe failed: {result.stderr.strip()}")

    try:
        payload = json.loads(result.stdout)
        streams = payload["streams"]
        video_stream = next(stream for stream in streams if stream["codec_type"] == "video")
        audio_stream = next((stream for stream in streams if stream["codec_type"] == "audio"), None)
        format_info = payload["format"]
        return VideoInfo(
            duration_seconds=float(format_info["duration"]),
            width=int(video_stream["width"]),
            height=int(video_stream["height"]),
            size_bytes=path.stat().st_size,
            container=format_info.get("format_name") or None,
            video_codec=video_stream.get("codec_name"),
            audio_codec=audio_stream.get("codec_name") if audio_stream else None,
            frame_rate=_parse_frame_rate(video_stream.get("r_frame_rate")),
            pixel_format=video_stream.get("pix_fmt"),
            video_profile=video_stream.get("profile"),
        )
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TranscodeError("ffprobe returned incomplete media metadata") from exc


def _scale_filter(spec: RenditionSpec) -> str:
    fit = f"scale={spec.width}:{spec.height}:force_original_aspect_ratio=decrease"
    if not spec.pad_to_fit:
        # Keep even dimensions; h264 rejects odd ones.
        return f"{fit},scale=trunc(iw/2)*2:trunc(ih/2)*2"
    pad = f"pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2:color=black"
    return f"{fit},{pad}"


def transcode(source: Path, destination: Path, spec: RenditionSpec) -> Path:
    """Encode `source` into `destination` according to `spec`."""
    ensure_ffmpeg()
    destination.parent.mkdir(parents=True, exist_ok=True)

    command = ["ffmpeg", "-y", "-i", str(source)]
    if spec.max_duration_seconds is not None:
        command += ["-t", str(spec.max_duration_seconds)]
    command += [
        "-vf", _scale_filter(spec),
        "-r", str(spec.fps),
        "-c:v", spec.video_codec,
        "-profile:v", spec.video_profile,
        "-pix_fmt", spec.pixel_format,
        "-b:v", spec.video_bitrate,
        "-preset", "medium",
        "-c:a", spec.audio_codec,
        "-b:a", spec.audio_bitrate,
        "-ar", str(spec.audio_sample_rate),
        "-f", spec.muxer,
        # Both platforms need the moov atom up front to begin processing
        # before the full file has landed.
        "-movflags", "+faststart",
        str(destination),
    ]

    log.info("transcode.start", source=str(source), target=str(destination))
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=TRANSCODE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise TranscodeError("ffmpeg timed out") from exc
    if result.returncode != 0:
        raise TranscodeError(f"ffmpeg failed: {result.stderr.strip()[-2000:]}")

    log.info("transcode.done", target=str(destination), bytes=destination.stat().st_size)
    return destination


def transcode_for(platform: Platform, source: Path, destination: Path) -> Path:
    return transcode(source, destination, SPECS[platform])

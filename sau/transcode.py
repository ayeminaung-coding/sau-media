"""ffmpeg/ffprobe wrappers producing per-platform renditions.

Each platform gets its own encode rather than a shared "good enough" file:
TikTok and Reels want vertical 9:16, a Facebook feed video keeps its native
aspect. Encoding once per platform costs CPU but avoids the platform doing a
worse job re-encoding for us.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sau.logging import get_logger
from sau.models import Platform

log = get_logger(__name__)


class TranscodeError(RuntimeError):
    """ffmpeg or ffprobe exited non-zero."""


@dataclass(frozen=True)
class VideoInfo:
    duration_seconds: float
    width: int
    height: int


@dataclass(frozen=True)
class RenditionSpec:
    """Target encode parameters for one platform."""

    width: int
    height: int
    video_bitrate: str
    audio_bitrate: str = "128k"
    fps: int = 30
    #: Hard trim, in seconds. `None` keeps the full duration.
    max_duration_seconds: int | None = None
    #: Letterbox/pillarbox to exactly width x height when True; otherwise the
    #: source aspect is preserved and only downscaled to fit.
    pad_to_fit: bool = True


#: Conservative targets. Both platforms re-encode on ingest anyway, so the
#: goal is a clean, spec-compliant master rather than a maximum-quality one.
SPECS: dict[Platform, RenditionSpec] = {
    Platform.TIKTOK: RenditionSpec(
        width=1080, height=1920, video_bitrate="6M", max_duration_seconds=600
    ),
    Platform.FACEBOOK_REEL: RenditionSpec(
        width=1080, height=1920, video_bitrate="6M", max_duration_seconds=90
    ),
    Platform.FACEBOOK_VIDEO: RenditionSpec(
        width=1920, height=1080, video_bitrate="8M", pad_to_fit=False
    ),
}


def ensure_ffmpeg() -> None:
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            raise TranscodeError(f"{binary} not found on PATH")


def probe(path: Path) -> VideoInfo:
    """Read duration and dimensions from the first video stream."""
    ensure_ffmpeg()
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise TranscodeError(f"ffprobe failed: {result.stderr.strip()}")

    payload = json.loads(result.stdout)
    stream = payload["streams"][0]
    return VideoInfo(
        duration_seconds=float(payload["format"]["duration"]),
        width=int(stream["width"]),
        height=int(stream["height"]),
    )


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
        "-c:v", "libx264",
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-b:v", spec.video_bitrate,
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", spec.audio_bitrate,
        "-ar", "44100",
        # Both platforms need the moov atom up front to begin processing
        # before the full file has landed.
        "-movflags", "+faststart",
        str(destination),
    ]

    log.info("transcode.start", source=str(source), target=str(destination))
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise TranscodeError(f"ffmpeg failed: {result.stderr.strip()[-2000:]}")

    log.info("transcode.done", target=str(destination), bytes=destination.stat().st_size)
    return destination


def transcode_for(platform: Platform, source: Path, destination: Path) -> Path:
    return transcode(source, destination, SPECS[platform])

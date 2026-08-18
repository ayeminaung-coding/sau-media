"""Facebook publishing for Page Reels and Page feed video.

Both publishers prefer the hosted (`file_url`) path when the media bucket has
a public domain: Meta pulls the file itself, which removes the chunk loop
entirely and keeps multi-gigabyte transfers off this process. The byte-pushing
paths remain as the fallback for private buckets.
"""

from __future__ import annotations

from typing import Any, ClassVar

from sau import storage
from sau.config import get_settings
from sau.errors import PlatformError
from sau.http import with_retries
from sau.logging import get_logger
from sau.models import JobState, Platform
from sau.platforms.base import Publisher, PublishRequest, PublishResult, StatusResult
from sau.platforms.facebook.client import FacebookClient

log = get_logger(__name__)

PERMALINK_HOST = "https://www.facebook.com"

#: `status.video_status` values that end the job.
_TERMINAL_STATUS = {"ready": JobState.PUBLISHED, "error": JobState.FAILED}


def _hosted_uploads_available() -> bool:
    return bool(get_settings().r2_public_base_url)


def _permalink(payload: dict[str, Any]) -> str | None:
    """Normalise Graph's relative `permalink_url` into an absolute URL."""
    raw = payload.get("permalink_url")
    if not raw:
        return None
    return f"{PERMALINK_HOST}{raw}" if raw.startswith("/") else str(raw)


class _FacebookPublisher(Publisher):
    """Shared status polling for both Facebook targets."""

    def check_status(self, external_id: str) -> StatusResult:
        with FacebookClient() as client:
            payload = with_retries(
                lambda: client.video_status(external_id), label="facebook.status"
            )

        status = payload.get("status") or {}
        video_status = str(status.get("video_status", "")).lower()
        state = _TERMINAL_STATUS.get(video_status, JobState.PROCESSING)

        if state is JobState.FAILED:
            phase = status.get("processing_phase") or status.get("uploading_phase") or {}
            reason = phase.get("error", {}).get("message") or video_status
            return StatusResult(state=state, error=f"facebook processing failed: {reason}")

        if state is JobState.PUBLISHED:
            return StatusResult(state=state, external_url=_permalink(payload))

        return StatusResult(state=state)


class FacebookReelPublisher(_FacebookPublisher):
    """Publishes to the Page's Reels shelf via a resumable upload session."""

    platform: ClassVar[Platform] = Platform.FACEBOOK_REEL

    def publish(self, request: PublishRequest) -> PublishResult:
        with FacebookClient() as client:
            video_id, upload_url = with_retries(
                client.start_reel_session, label="facebook.reel.start"
            )

            if _hosted_uploads_available():
                file_url = storage.public_url(request.storage_key)
                with_retries(
                    lambda: client.upload_reel_from_url(upload_url, file_url),
                    label="facebook.reel.hosted",
                )
                request.on_progress(request.size_bytes)
            else:
                self._push_bytes(client, upload_url, video_id, request)

            with_retries(
                lambda: client.finish_reel(video_id, request.caption),
                label="facebook.reel.finish",
            )

        log.info("facebook.reel.published", job_id=request.job_id, video_id=video_id)
        return PublishResult(external_id=video_id, state=JobState.PROCESSING)

    def _push_bytes(
        self, client: FacebookClient, upload_url: str, video_id: str, request: PublishRequest
    ) -> None:
        """Stream the file into the session, resuming from the server offset.

        Meta reports how many bytes it actually holds, so a retry after a
        dropped connection re-reads that offset rather than trusting our own
        counter.
        """
        offset = self._server_offset(client, video_id, fallback=request.resume_offset)
        chunk_size = get_settings().chunk_size_bytes

        for chunk_offset, payload in storage.iter_chunks(
            request.storage_key, chunk_size, start=offset
        ):
            with_retries(
                lambda p=payload, o=chunk_offset: client.upload_reel_bytes(  # type: ignore[misc]
                    upload_url, p, o, request.size_bytes
                ),
                label="facebook.reel.chunk",
            )
            request.on_progress(chunk_offset + len(payload))
            log.info(
                "facebook.reel.chunk.sent",
                job_id=request.job_id, offset=chunk_offset, length=len(payload),
            )

    def _server_offset(self, client: FacebookClient, video_id: str, *, fallback: int) -> int:
        """Ask Meta how much of the file it already accepted."""
        try:
            status = client.video_status(video_id).get("status") or {}
            transferred = (status.get("uploading_phase") or {}).get("bytes_transferred")
            return int(transferred) if transferred is not None else fallback
        except PlatformError:
            return fallback


class FacebookVideoPublisher(_FacebookPublisher):
    """Publishes a full-length video to the Page feed.

    Uses the phased upload where Meta, not this code, decides each chunk
    window: the transfer response carries the next `start_offset`/`end_offset`
    pair and the loop simply follows it until they converge.
    """

    platform: ClassVar[Platform] = Platform.FACEBOOK_VIDEO

    def publish(self, request: PublishRequest) -> PublishResult:
        with FacebookClient() as client:
            if _hosted_uploads_available():
                file_url = storage.public_url(request.storage_key)
                video_id = with_retries(
                    lambda: client.create_video_from_url(file_url, request.caption),
                    label="facebook.video.hosted",
                )
                request.on_progress(request.size_bytes)
            else:
                video_id = self._chunked_publish(client, request)

        log.info("facebook.video.published", job_id=request.job_id, video_id=video_id)
        return PublishResult(external_id=video_id, state=JobState.PROCESSING)

    def _chunked_publish(self, client: FacebookClient, request: PublishRequest) -> str:
        session = with_retries(
            lambda: client.start_video_session(request.size_bytes),
            label="facebook.video.start",
        )
        session_id = str(session["upload_session_id"])
        video_id = str(session["video_id"])
        start, end = int(session["start_offset"]), int(session["end_offset"])

        while start < end:
            chunk = storage.read_range(request.storage_key, start, end - start)
            response = with_retries(
                lambda c=chunk, s=start: client.transfer_video_chunk(  # type: ignore[misc]
                    session_id, s, c
                ),
                label="facebook.video.chunk",
            )
            log.info(
                "facebook.video.chunk.sent",
                job_id=request.job_id, offset=start, length=len(chunk),
            )
            start, end = int(response["start_offset"]), int(response["end_offset"])
            request.on_progress(start)

        with_retries(
            lambda: client.finish_video_session(session_id, request.caption),
            label="facebook.video.finish",
        )
        return video_id

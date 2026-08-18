"""TikTok publishing.

Two transfer modes exist and the default is deliberate:

* ``PULL_FROM_URL`` — we hand TikTok a URL and it fetches the file. No chunk
  loop, no retry bookkeeping, and on R2 the egress is free. Requires a domain
  verified in TikTok's developer portal, so it is opt-in via
  ``TIKTOK_PULL_FROM_URL``.
* ``FILE_UPLOAD`` — we PUT the bytes ourselves. The default, and the only
  option without a verified custom domain. TikTok exposes no "resume at
  offset" endpoint for these sessions, so a failed transfer restarts from a
  fresh init.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar

from sau import storage
from sau.config import get_settings
from sau.errors import PlatformError
from sau.http import with_retries
from sau.logging import get_logger
from sau.models import JobState, Platform
from sau.platforms.base import Publisher, PublishRequest, PublishResult, StatusResult
from sau.platforms.tiktok.client import PLATFORM, TikTokClient

log = get_logger(__name__)

MIN_CHUNK_BYTES = 5 * 1024 * 1024
MAX_CHUNK_BYTES = 64 * 1024 * 1024
MAX_CHUNKS = 1000

#: TikTok rejects titles longer than this.
MAX_TITLE_CHARS = 2200

_STATUS_MAP = {
    "PROCESSING_UPLOAD": JobState.PROCESSING,
    "PROCESSING_DOWNLOAD": JobState.PROCESSING,
    "PUBLISH_COMPLETE": JobState.PUBLISHED,
    "SEND_TO_USER_INBOX": JobState.PUBLISHED,
    "FAILED": JobState.FAILED,
}


@dataclass(frozen=True)
class ChunkPlan:
    chunk_size: int
    total_chunks: int


def plan_chunks(size_bytes: int, preferred_chunk: int) -> ChunkPlan:
    """Pick a chunk size satisfying TikTok's constraints.

    The rules: chunks are 5-64 MiB, at most 1000 of them, and the *final*
    chunk absorbs the remainder rather than being a short chunk of its own.
    A file below the 5 MiB minimum must be sent as a single chunk.
    """
    if size_bytes <= 0:
        raise ValueError("size_bytes must be positive")

    if size_bytes < MIN_CHUNK_BYTES:
        return ChunkPlan(chunk_size=size_bytes, total_chunks=1)

    chunk = min(max(preferred_chunk, MIN_CHUNK_BYTES), MAX_CHUNK_BYTES)

    if size_bytes // chunk > MAX_CHUNKS:
        chunk = min(math.ceil(size_bytes / MAX_CHUNKS), MAX_CHUNK_BYTES)
        if size_bytes // chunk > MAX_CHUNKS:
            raise PlatformError(
                f"video of {size_bytes} bytes exceeds the chunked-upload ceiling",
                platform=PLATFORM,
            )

    return ChunkPlan(chunk_size=chunk, total_chunks=max(1, size_bytes // chunk))


def iter_ranges(size_bytes: int, plan: ChunkPlan) -> Iterator[tuple[int, int]]:
    """Yield `(offset, length)` per chunk; the last one runs to end of file."""
    for index in range(plan.total_chunks - 1):
        yield index * plan.chunk_size, plan.chunk_size

    tail_offset = (plan.total_chunks - 1) * plan.chunk_size
    yield tail_offset, size_bytes - tail_offset


class TikTokPublisher(Publisher):
    platform: ClassVar[Platform] = Platform.TIKTOK

    def __init__(self, *, prefer_pull: bool = True) -> None:
        settings = get_settings()
        # PULL_FROM_URL needs a domain verified in TikTok's portal, which is a
        # stricter bar than merely being public: an r2.dev development URL is
        # reachable but unverifiable, and init would fail with
        # `url_ownership_unverified`. Chunked upload is the correct default.
        self._prefer_pull = (
            prefer_pull and settings.tiktok_pull_from_url and bool(settings.r2_public_base_url)
        )

    # -- publishing -------------------------------------------------------

    def publish(self, request: PublishRequest) -> PublishResult:
        with TikTokClient() as client:
            post_info = self._build_post_info(client, request)

            if self._prefer_pull:
                publish_id = self._publish_by_pull(client, post_info, request)
            else:
                publish_id = self._publish_by_upload(client, post_info, request)

        log.info("tiktok.publish.started", job_id=request.job_id, publish_id=publish_id)
        return PublishResult(external_id=publish_id, state=JobState.PROCESSING)

    def _build_post_info(self, client: TikTokClient, request: PublishRequest) -> dict[str, Any]:
        """Assemble `post_info`, validating privacy against the account.

        An app that has not passed TikTok's audit is restricted to
        `SELF_ONLY`; asking for anything else fails at init, so the allowed
        set is read from the creator first and the request is clamped to it.
        """
        creator = client.query_creator_info()
        allowed = creator.get("privacy_level_options") or ["SELF_ONLY"]

        privacy = request.privacy if request.privacy in allowed else allowed[0]
        if privacy != request.privacy:
            log.warning(
                "tiktok.privacy.clamped",
                job_id=request.job_id, requested=request.privacy, applied=privacy,
            )

        return {
            "title": request.caption[:MAX_TITLE_CHARS],
            "privacy_level": privacy,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,
        }

    def _publish_by_pull(
        self, client: TikTokClient, post_info: dict[str, Any], request: PublishRequest
    ) -> str:
        url = storage.public_url(request.storage_key)
        data = with_retries(
            lambda: client.init_pull_from_url(post_info, url), label="tiktok.init.pull"
        )
        request.on_progress(request.size_bytes)
        return str(data["publish_id"])

    def _publish_by_upload(
        self, client: TikTokClient, post_info: dict[str, Any], request: PublishRequest
    ) -> str:
        plan = plan_chunks(request.size_bytes, get_settings().chunk_size_bytes)
        data = with_retries(
            lambda: client.init_file_upload(
                post_info, request.size_bytes, plan.chunk_size, plan.total_chunks
            ),
            label="tiktok.init.upload",
        )
        publish_id = str(data["publish_id"])
        upload_url = str(data["upload_url"])

        for offset, length in iter_ranges(request.size_bytes, plan):
            payload = storage.read_range(request.storage_key, offset, length)
            with_retries(
                lambda p=payload, o=offset: client.upload_chunk(  # type: ignore[misc]
                    upload_url, p, o, request.size_bytes
                ),
                label="tiktok.chunk",
            )
            request.on_progress(offset + length)
            log.info(
                "tiktok.chunk.sent",
                job_id=request.job_id, offset=offset, length=length, total=request.size_bytes,
            )

        return publish_id

    # -- polling ----------------------------------------------------------

    def check_status(self, external_id: str) -> StatusResult:
        with TikTokClient() as client:
            data = with_retries(
                lambda: client.fetch_status(external_id), label="tiktok.status"
            )
            raw_status = str(data.get("status", ""))
            state = _STATUS_MAP.get(raw_status, JobState.PROCESSING)

            if state is JobState.FAILED:
                reason = data.get("fail_reason") or raw_status
                return StatusResult(state=state, error=f"tiktok publish failed: {reason}")

            if state is JobState.PUBLISHED:
                return StatusResult(state=state, external_url=self._post_url(client, data))

            return StatusResult(state=state)

    def _post_url(self, client: TikTokClient, data: dict[str, Any]) -> str | None:
        """Build a permalink from the completed publish, if one is exposed.

        Note the field name is misspelled in TikTok's API, not here.
        """
        post_ids = data.get("publicaly_available_post_id") or []
        if not post_ids:
            return None
        username = client.query_creator_info().get("creator_username")
        if not username:
            return None
        return f"https://www.tiktok.com/@{username}/video/{post_ids[0]}"

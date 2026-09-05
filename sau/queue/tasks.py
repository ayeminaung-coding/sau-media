"""Worker tasks.

Work is split at the two points where control leaves this process:

``run_publish_job``   transfer bytes, start the platform publish.
``poll_publish_job``  ask the platform whether encoding has finished.

Each database transaction here is deliberately short. A publish can take ten
minutes; holding a transaction open across it would pin a connection and, more
importantly, lock the job row against the progress writes that the upload
itself emits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sau.db import session_scope
from sau.errors import PlatformError
from sau.logging import get_logger
from sau.models import JobState, Platform, PublishJob
from sau.platforms import get_publisher
from sau.platforms.base import PublishRequest
from sau.queue import queue_for
from sau.renditions import ensure_rendition

log = get_logger(__name__)

#: Whole-task attempts, distinct from the HTTP-level retries in `sau.http`.
#: This bound also covers a worker that died mid-transfer.
MAX_ATTEMPTS = 3

#: Platform-side encoding is polled on a fixed cadence up to a ceiling.
POLL_INTERVAL = timedelta(seconds=30)
MAX_POLLS = 80  # ~40 minutes


@dataclass(frozen=True)
class _JobContext:
    """The job fields the transfer needs, read once so the session can close."""

    job_id: str
    platform: Platform
    caption: str
    title: str
    privacy: str
    resume_offset: int
    attempts: int


# --- small, single-purpose transactions -------------------------------------


def _claim(job_id: str) -> _JobContext | None:
    """Take ownership of a job for this attempt, or decline it.

    Returns `None` when the job is missing, already finished, or out of
    attempts; the caller then does nothing.
    """
    with session_scope() as session:
        job = session.get(PublishJob, job_id)
        if job is None:
            log.warning("job.missing", job_id=job_id)
            return None
        if job.is_terminal:
            log.info("job.already_terminal", job_id=job_id, state=job.state.value)
            return None
        # A backlog job reaching a worker means something enqueued it without
        # going through `release_asset`. Publishing it would post content on a
        # day the schedule never chose, so decline rather than run it.
        if job.state is JobState.SCHEDULED:
            log.warning("job.not_released", job_id=job_id)
            return None

        job.attempts += 1
        if job.attempts > MAX_ATTEMPTS:
            _mark_failed(job, f"exhausted {MAX_ATTEMPTS} attempts")
            return None

        job.state = JobState.UPLOADING
        return _JobContext(
            job_id=job.id,
            platform=job.platform,
            caption=job.caption,
            title=job.title,
            privacy=job.privacy,
            resume_offset=job.uploaded_bytes,
            attempts=job.attempts,
        )


def _mark_failed(job: PublishJob, message: str) -> None:
    """Move a job to FAILED. Caller owns the surrounding transaction."""
    job.state = JobState.FAILED
    job.last_error = message[:2000]
    log.error("job.failed", job_id=job.id, platform=job.platform.value, error=message)


def _set_state(job_id: str, state: JobState) -> None:
    with session_scope() as session:
        job = session.get(PublishJob, job_id)
        if job is not None:
            job.state = state


def _record_progress(job_id: str, uploaded_bytes: int) -> None:
    """Persist transfer progress so a resumed attempt can skip ahead."""
    with session_scope() as session:
        job = session.get(PublishJob, job_id)
        if job is not None:
            job.uploaded_bytes = uploaded_bytes


def _record_failure(ctx: _JobContext, error: PlatformError) -> bool:
    """Store the error and report whether the job should be re-queued."""
    retry = error.retryable and ctx.attempts < MAX_ATTEMPTS
    with session_scope() as session:
        job = session.get(PublishJob, ctx.job_id)
        if job is None:
            return False
        if retry:
            job.state = JobState.PENDING
            job.last_error = str(error)[:2000]
        else:
            _mark_failed(job, str(error))
    return retry


def _record_started(job_id: str, external_id: str, state: JobState, url: str | None) -> None:
    with session_scope() as session:
        job = session.get(PublishJob, job_id)
        if job is None:
            return
        job.external_id = external_id
        job.external_url = url
        job.state = state
        job.last_error = None


# --- tasks ------------------------------------------------------------------


def run_publish_job(job_id: str) -> None:
    """Transfer the source object and start the platform-side publish."""
    ctx = _claim(job_id)
    if ctx is None:
        return

    try:
        with session_scope() as session:
            job = session.get(PublishJob, job_id)
            if job is None:
                return
            rendition = ensure_rendition(session, job.asset, ctx.platform)
            storage_key, size_bytes = rendition.storage_key, rendition.size_bytes

        _set_state(job_id, JobState.UPLOADING)

        result = get_publisher(ctx.platform).publish(
            PublishRequest(
                job_id=ctx.job_id,
                storage_key=storage_key,
                size_bytes=size_bytes,
                caption=ctx.caption,
                title=ctx.title,
                privacy=ctx.privacy,
                resume_offset=ctx.resume_offset,
                on_progress=lambda uploaded: _record_progress(job_id, uploaded),
            )
        )
    except PlatformError as exc:
        if _record_failure(ctx, exc):
            log.warning("job.retrying", job_id=job_id, attempt=ctx.attempts, error=str(exc))
            queue_for(ctx.platform).enqueue_in(POLL_INTERVAL, run_publish_job, job_id)
        return
    except Exception as exc:  # record the cause, then let the queue see it fail
        with session_scope() as session:
            job = session.get(PublishJob, job_id)
            if job is not None:
                _mark_failed(job, f"unexpected error: {exc!r}")
        raise

    _record_started(job_id, result.external_id, result.state, result.external_url)
    log.info("job.transferred", job_id=job_id, external_id=result.external_id)

    if result.state is JobState.PROCESSING:
        queue_for(ctx.platform).enqueue_in(POLL_INTERVAL, poll_publish_job, job_id, 1)


def poll_publish_job(job_id: str, poll_count: int = 1) -> None:
    """Check whether the platform finished encoding, re-scheduling if not."""
    with session_scope() as session:
        job = session.get(PublishJob, job_id)
        if job is None or job.is_terminal:
            return
        if not job.external_id:
            _mark_failed(job, "polled a job with no external id")
            return
        platform, external_id = job.platform, job.external_id

    try:
        status = get_publisher(platform).check_status(external_id)
    except PlatformError as exc:
        if not exc.retryable:
            with session_scope() as session:
                job = session.get(PublishJob, job_id)
                if job is not None:
                    _mark_failed(job, str(exc))
            return
        status = None  # transient; fall through and poll again

    if status is not None and status.state is not JobState.PROCESSING:
        with session_scope() as session:
            job = session.get(PublishJob, job_id)
            if job is None:
                return
            job.state = status.state
            job.external_url = status.external_url or job.external_url
            job.last_error = status.error
            log.info("job.settled", job_id=job_id, state=job.state.value, url=job.external_url)
        return

    if poll_count >= MAX_POLLS:
        with session_scope() as session:
            job = session.get(PublishJob, job_id)
            if job is not None:
                _mark_failed(job, f"still processing after {MAX_POLLS} polls")
        return

    queue_for(platform).enqueue_in(POLL_INTERVAL, poll_publish_job, job_id, poll_count + 1)


def dispatch(job_ids: list[str]) -> None:
    """Fan a batch of freshly created jobs out to their platform queues."""
    with session_scope() as session:
        found = {
            job.id: job.platform
            for job in (session.get(PublishJob, job_id) for job_id in job_ids)
            if job is not None
        }

    for job_id, platform in found.items():
        queue_for(platform).enqueue(run_publish_job, job_id)
        log.info("job.dispatched", job_id=job_id, platform=platform.value)

    # A row that cannot be read here is never retried by anything: it simply
    # stays pending with no error attached. Dropping it quietly makes that
    # state indistinguishable from a queue that is merely slow, so say so.
    missing = [job_id for job_id in job_ids if job_id not in found]
    if missing:
        log.error("job.dispatch.missing", job_ids=missing)
        raise RuntimeError(f"jobs not found at dispatch, left unqueued: {', '.join(missing)}")

"""FastAPI application.

The upload of the source file goes *directly* to object storage via a
presigned URL — it never passes through this process. That is what keeps a
4 GB Facebook video from pinning the API's memory and request timeout.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import PurePosixPath

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from sau import __version__, storage
from sau.api.schemas import (
    AssetResponse,
    BacklogEntry,
    JobResponse,
    PublishRequestBody,
    PublishResponse,
    RegisterAssetRequest,
    UploadUrlRequest,
    UploadUrlResponse,
)
from sau.config import get_settings
from sau.db import session_scope
from sau.logging import configure_logging, get_logger
from sau.models import Asset, JobState, PublishJob
from sau.queue.tasks import dispatch

log = get_logger(__name__)

UPLOAD_URL_TTL_SECONDS = 3600

router = APIRouter()


def get_session() -> Iterator[Session]:  # pragma: no cover - dependency plumbing
    with session_scope() as session:
        yield session


def _load_job(session: Session, job_id: str) -> PublishJob:
    job = session.get(PublishJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="job not found")
    return job


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.post("/assets/upload-url", response_model=UploadUrlResponse)
def create_upload_url(body: UploadUrlRequest) -> UploadUrlResponse:
    """Mint a presigned PUT URL for the client to upload the source video to."""
    suffix = PurePosixPath(body.filename).suffix or ".mp4"
    key = f"sources/{uuid.uuid4()}{suffix}"
    try:
        url = storage.presigned_upload_url(key, UPLOAD_URL_TTL_SECONDS, body.content_type)
    except RuntimeError as exc:
        # Signing is local, so this only fires on misconfigured storage. Report
        # it here: the alternative is handing the client a URL pointing at a
        # host that does not exist, which fails much later and far less clearly.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return UploadUrlResponse(
        storage_key=key,
        upload_url=url,
        expires_seconds=UPLOAD_URL_TTL_SECONDS,
    )


@router.post("/assets", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
def register_asset(body: RegisterAssetRequest, session: Session = Depends(get_session)) -> Asset:
    """Register an already-uploaded object as a publishable asset.

    Only the size is read here; duration and dimensions are filled in by the
    first transcode, which already has the file on local disk.
    """
    try:
        size_bytes = storage.size_of(body.storage_key)
    except Exception as exc:  # any storage failure is a bad key from the caller
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"object not readable: {exc}"
        ) from exc

    asset = Asset(storage_key=body.storage_key, size_bytes=size_bytes)
    session.add(asset)
    session.flush()
    log.info("asset.registered", asset_id=asset.id, bytes=size_bytes)
    return asset


@router.get("/assets/{asset_id}", response_model=AssetResponse)
def get_asset(asset_id: str, session: Session = Depends(get_session)) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="asset not found")
    return asset


@router.post("/publish", response_model=PublishResponse, status_code=status.HTTP_202_ACCEPTED)
def publish(
    body: PublishRequestBody,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> PublishResponse:
    """Fan one asset out to one independent job per platform."""
    asset = session.get(Asset, body.asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="asset not found")

    existing = {job.platform for job in asset.jobs}
    duplicates = [t.platform.value for t in body.targets if t.platform in existing]
    if duplicates:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"asset already has jobs for: {', '.join(duplicates)}",
        )

    jobs = [
        PublishJob(
            asset_id=asset.id,
            platform=target.platform,
            caption=target.caption,
            title=target.title,
            privacy=target.privacy,
            state=JobState.SCHEDULED if body.schedule else JobState.PENDING,
        )
        for target in body.targets
    ]
    session.add_all(jobs)
    session.flush()

    responses = [JobResponse.model_validate(job) for job in jobs]
    job_ids = [job.id for job in jobs]

    # A scheduled asset is queued by `release_asset`, not here.
    if body.schedule:
        log.info("publish.scheduled", asset_id=asset.id, jobs=len(job_ids))
        return PublishResponse(asset_id=asset.id, jobs=responses)

    # Commit before scheduling, not after: Starlette runs background tasks
    # *before* a yield-dependency's teardown, so relying on `get_session` to
    # commit would hand `dispatch` ids that no other connection can see yet.
    # It would then find nothing, enqueue nothing, and leave the jobs pending
    # forever with no error anywhere.
    session.commit()
    background.add_task(dispatch, job_ids)

    return PublishResponse(asset_id=asset.id, jobs=responses)


@router.get("/schedule", response_model=list[BacklogEntry])
def list_schedule(limit: int = 50, session: Session = Depends(get_session)) -> list[BacklogEntry]:
    """Return the backlog, oldest first — the order it will be published in.

    Grouped by asset because that is the unit released: one asset goes out per
    slot, carrying every platform it was queued for.
    """
    rows = list(
        session.execute(
            select(PublishJob)
            .where(PublishJob.state == JobState.SCHEDULED)
            .order_by(PublishJob.created_at)
        ).scalars()
    )

    entries: dict[str, BacklogEntry] = {}
    for job in rows:
        entry = entries.get(job.asset_id)
        if entry is None:
            if len(entries) >= limit:
                continue
            entry = BacklogEntry(asset_id=job.asset_id, created_at=job.created_at, jobs=[])
            entries[job.asset_id] = entry
        entry.jobs.append(JobResponse.model_validate(job))
    return list(entries.values())


@router.post("/assets/{asset_id}/release", response_model=PublishResponse)
def release_asset(
    asset_id: str,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> PublishResponse:
    """Publish a scheduled asset now. This is what the daily cron calls."""
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="asset not found")

    scheduled = [job for job in asset.jobs if job.state is JobState.SCHEDULED]
    if not scheduled:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="asset has no scheduled jobs")

    for job in scheduled:
        job.state = JobState.PENDING

    responses = [JobResponse.model_validate(job) for job in scheduled]
    job_ids = [job.id for job in scheduled]

    # Same ordering constraint as `publish`: commit before the task is queued.
    session.commit()
    background.add_task(dispatch, job_ids)
    log.info("publish.released", asset_id=asset.id, jobs=len(job_ids))

    return PublishResponse(asset_id=asset.id, jobs=responses)


@router.delete("/assets/{asset_id}/schedule", status_code=status.HTTP_204_NO_CONTENT)
def unschedule_asset(asset_id: str, session: Session = Depends(get_session)) -> None:
    """Drop an asset from the backlog.

    Only ever deletes SCHEDULED rows, so a job already in flight on a worker
    cannot be cancelled through this path.
    """
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="asset not found")

    for job in list(asset.jobs):
        if job.state is JobState.SCHEDULED:
            session.delete(job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, session: Session = Depends(get_session)) -> PublishJob:
    return _load_job(session, job_id)


@router.get("/assets/{asset_id}/jobs", response_model=list[JobResponse])
def list_asset_jobs(asset_id: str, session: Session = Depends(get_session)) -> list[PublishJob]:
    return list(
        session.execute(select(PublishJob).where(PublishJob.asset_id == asset_id)).scalars()
    )


@router.post("/jobs/{job_id}/retry", response_model=JobResponse)
def retry_job(
    job_id: str,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> PublishJob:
    """Re-queue a failed job without touching its siblings."""
    job = _load_job(session, job_id)
    if job.state is not JobState.FAILED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"job is {job.state.value}, not failed"
        )

    job.state = JobState.PENDING
    job.attempts = 0
    job.last_error = None
    # Same ordering constraint as `publish`: commit before the task is queued.
    session.commit()
    background.add_task(dispatch, [job.id])
    return job


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Socials Auto Upload", version=__version__)
    # The console is a static page on a different origin; it calls this API
    # from the browser and reads nothing but its own JSON.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()

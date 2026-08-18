"""Series endpoints: episodes, their captions, and publishing them in order.

A series changes nothing about the fan-out. Publishing part 3 creates the same
independent `PublishJob` per platform that a one-off upload does; the series
only decides what the caption says and what order the parts leave the backlog
in.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from sau.api.deps import get_session, register_asset_row
from sau.api.schemas import (
    CaptionPreview,
    GenerateHooksRequest,
    GenerateHooksResponse,
    JobResponse,
    PartUpdate,
    PublishResponse,
    RegisterPartRequest,
    SeriesCreate,
    SeriesPartResponse,
    SeriesPublishRequest,
    SeriesResponse,
    SeriesUpdate,
)
from sau.captions.generate import PartBrief, generate_hooks
from sau.captions.providers import CaptionError
from sau.captions.template import SeriesCopy, render
from sau.logging import get_logger
from sau.models import (
    CAPTION_LIMITS,
    TITLE_LIMITS,
    JobState,
    Platform,
    PublishJob,
    Series,
    SeriesPart,
)
from sau.queue.tasks import dispatch
from sau.series import SeriesNameError, missing_parts, parse_part, try_parse_part

log = get_logger(__name__)

router = APIRouter(prefix="/series", tags=["series"])


def _load(session: Session, ref: str) -> Series:
    """Resolve a series by id or by slug — the slug is what a human types."""
    series = session.get(Series, ref)
    if series is None:
        series = session.execute(select(Series).where(Series.slug == ref)).scalar_one_or_none()
    if series is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="series not found")
    return series


def _parsed_label(filename: str) -> str:
    """The descriptive tail of a series filename, or empty if it has none."""
    parsed = try_parse_part(filename)
    return parsed.label if parsed else ""


def _ordered_parts(series: Series) -> list[SeriesPart]:
    return sorted(series.parts, key=lambda p: p.part_index)


def _effective_total(series: Series) -> int:
    """What `{total}` renders as: the declared count, or what is registered."""
    return series.total_parts or len(series.parts)


def _to_response(session: Session, series: Series) -> SeriesResponse:
    parts = _ordered_parts(series)
    asset_ids = [p.asset_id for p in parts]

    jobs_by_asset: dict[str, list[PublishJob]] = {}
    if asset_ids:
        rows = session.execute(
            select(PublishJob).where(PublishJob.asset_id.in_(asset_ids))
        ).scalars()
        for job in rows:
            jobs_by_asset.setdefault(job.asset_id, []).append(job)

    part_responses = [
        SeriesPartResponse(
            id=part.id,
            series_id=part.series_id,
            asset_id=part.asset_id,
            part_index=part.part_index,
            hook=part.hook,
            source_filename=part.source_filename,
            duration_seconds=part.asset.duration_seconds if part.asset else None,
            jobs=[JobResponse.model_validate(j) for j in jobs_by_asset.get(part.asset_id, [])],
            created_at=part.created_at,
        )
        for part in parts
    ]

    return SeriesResponse(
        id=series.id,
        slug=series.slug,
        title_local=series.title_local,
        title_en=series.title_en,
        synopsis=series.synopsis,
        language=series.language,
        style_example=series.style_example,
        total_parts=series.total_parts,
        caption_template=series.caption_template,
        title_template=series.title_template,
        next_teaser_template=series.next_teaser_template,
        hashtags=dict(series.hashtags or {}),
        default_targets=[Platform(p) for p in (series.default_targets or [])],
        default_privacy=series.default_privacy,
        created_at=series.created_at,
        parts=part_responses,
        missing_parts=missing_parts(p.part_index for p in parts),
        effective_total=_effective_total(series),
    )


@router.post("", response_model=SeriesResponse, status_code=status.HTTP_201_CREATED)
def create_series(body: SeriesCreate, session: Session = Depends(get_session)) -> SeriesResponse:
    existing = session.execute(
        select(Series).where(Series.slug == body.slug)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"slug {body.slug!r} is taken")

    series = Series(
        slug=body.slug,
        title_local=body.title_local,
        title_en=body.title_en,
        synopsis=body.synopsis,
        language=body.language,
        style_example=body.style_example,
        total_parts=body.total_parts,
        caption_template=body.caption_template,
        title_template=body.title_template,
        next_teaser_template=body.next_teaser_template,
        hashtags=dict(body.hashtags),
        default_targets=[p.value for p in body.default_targets],
        default_privacy=body.default_privacy,
    )
    session.add(series)
    session.flush()
    log.info("series.created", series_id=series.id, slug=series.slug)
    return _to_response(session, series)


@router.get("", response_model=list[SeriesResponse])
def list_series(session: Session = Depends(get_session)) -> list[SeriesResponse]:
    rows = session.execute(select(Series).order_by(Series.created_at.desc())).scalars()
    return [_to_response(session, series) for series in rows]


@router.get("/{ref}", response_model=SeriesResponse)
def get_series(ref: str, session: Session = Depends(get_session)) -> SeriesResponse:
    return _to_response(session, _load(session, ref))


@router.patch("/{ref}", response_model=SeriesResponse)
def update_series(
    ref: str, body: SeriesUpdate, session: Session = Depends(get_session)
) -> SeriesResponse:
    series = _load(session, ref)
    fields = body.model_dump(exclude_unset=True)

    if "default_targets" in fields and fields["default_targets"] is not None:
        fields["default_targets"] = [Platform(p).value for p in fields["default_targets"]]

    for name, value in fields.items():
        # An explicit null only clears `total_parts`, which is genuinely
        # nullable; for the rest it means "not sent" and must not blank a
        # stored template.
        if value is None and name != "total_parts":
            continue
        setattr(series, name, value)

    session.flush()
    return _to_response(session, series)


@router.delete("/{ref}", status_code=status.HTTP_204_NO_CONTENT)
def delete_series(ref: str, session: Session = Depends(get_session)) -> None:
    """Delete a series and its part records.

    The assets and any jobs they already have survive: deleting a series is
    tidying up the grouping, not retracting what was published from it.
    """
    session.delete(_load(session, ref))


@router.post("/{ref}/parts", response_model=SeriesPartResponse, status_code=status.HTTP_201_CREATED)
def register_part(
    ref: str, body: RegisterPartRequest, session: Session = Depends(get_session)
) -> SeriesPartResponse:
    """Attach an uploaded object to a series, taking its number from the name."""
    series = _load(session, ref)

    if body.part_index is not None:
        index = body.part_index
    else:
        try:
            index = parse_part(body.filename).index
        except SeriesNameError as exc:
            # A 422 rather than a guess: an unparseable name is an operator
            # mistake, and inventing a position for it is how a series ends up
            # publishing in the wrong order.
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    clash = next((p for p in series.parts if p.part_index == index), None)
    if clash is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"part {index} is already registered "
                f"({clash.source_filename or clash.asset_id})"
            ),
        )

    asset = register_asset_row(session, body.storage_key)

    # `part1_movieName.mp4` already carries the title, so a series created with
    # only a slug names itself from its first episode. Only ever fills a blank:
    # a title the operator typed is never overwritten by a filename.
    if not series.title_local:
        label = _parsed_label(body.filename)
        if label:
            series.title_local = label[:255]
            log.info("series.title.derived", series_id=series.id, title=series.title_local)

    part = SeriesPart(
        series_id=series.id,
        asset_id=asset.id,
        part_index=index,
        hook=body.hook,
        source_filename=body.filename,
    )
    session.add(part)
    session.flush()
    log.info("series.part.registered", series_id=series.id, part=index, asset_id=asset.id)

    return SeriesPartResponse(
        id=part.id,
        series_id=part.series_id,
        asset_id=part.asset_id,
        part_index=part.part_index,
        hook=part.hook,
        source_filename=part.source_filename,
        duration_seconds=asset.duration_seconds,
        jobs=[],
        created_at=part.created_at,
    )


@router.patch("/{ref}/parts/{part_id}", response_model=SeriesResponse)
def update_part(
    ref: str, part_id: str, body: PartUpdate, session: Session = Depends(get_session)
) -> SeriesResponse:
    series = _load(session, ref)
    part = next((p for p in series.parts if p.id == part_id), None)
    if part is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="part not found")

    if body.part_index is not None and body.part_index != part.part_index:
        if any(p.part_index == body.part_index for p in series.parts):
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail=f"part {body.part_index} already exists"
            )
        part.part_index = body.part_index
    if body.hook is not None:
        part.hook = body.hook

    session.flush()
    return _to_response(session, series)


@router.delete("/{ref}/parts/{part_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_part(ref: str, part_id: str, session: Session = Depends(get_session)) -> None:
    series = _load(session, ref)
    part = next((p for p in series.parts if p.id == part_id), None)
    if part is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="part not found")
    session.delete(part)


@router.get("/{ref}/parts/{part_id}/preview", response_model=list[CaptionPreview])
def preview_part(
    ref: str, part_id: str, session: Session = Depends(get_session)
) -> list[CaptionPreview]:
    """Render one part exactly as it would publish, on every platform.

    Rendered through the same function the publish path uses, so the preview
    cannot drift from what actually goes out.
    """
    series = _load(session, ref)
    part = next((p for p in series.parts if p.id == part_id), None)
    if part is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="part not found")

    copy = SeriesCopy.from_series(series)
    total = _effective_total(series)

    previews = []
    for platform in Platform:
        rendered = render(
            copy,
            part_index=part.part_index,
            total=total,
            hook=part.hook,
            platform=platform,
        )
        previews.append(
            CaptionPreview(
                platform=platform,
                caption=rendered.caption,
                title=rendered.title,
                caption_limit=CAPTION_LIMITS[platform],
                title_limit=TITLE_LIMITS[platform],
            )
        )
    return previews


@router.post("/{ref}/generate-hooks", response_model=GenerateHooksResponse)
def generate_series_hooks(
    ref: str, body: GenerateHooksRequest, session: Session = Depends(get_session)
) -> GenerateHooksResponse:
    """Draft the per-episode hook for the whole series in one call.

    One call for every part, not one per part: a model asked for a single
    episode's hook cannot write a cliffhanger, because it does not know what
    the next episode opens with.
    """
    series = _load(session, ref)
    parts = _ordered_parts(series)
    if not parts:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="series has no parts yet")

    briefs = [
        PartBrief(
            index=part.part_index,
            label=part.source_filename,
            duration_seconds=part.asset.duration_seconds if part.asset else None,
            # Settled hooks are shown to the model as fixed unless the operator
            # asked to overwrite, so a re-run extends the arc instead of
            # rewriting lines that were already approved.
            hook="" if body.overwrite else part.hook,
        )
        for part in parts
    ]

    try:
        hooks, provider = generate_hooks(
            SeriesCopy.from_series(series),
            briefs,
            language=body.language,
            max_chars=body.max_chars,
        )
    except CaptionError as exc:
        # 502, not 500: the generator is an upstream this service depends on,
        # and every one of them being unavailable is not a bug in here. The
        # templates still render; the hooks are just not drafted.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    updated = 0
    for part in parts:
        hook = hooks.get(part.part_index)
        if hook and (body.overwrite or not part.hook.strip()):
            part.hook = hook
            updated += 1

    session.flush()
    log.info("series.hooks.generated", series_id=series.id, provider=provider, updated=updated)
    return GenerateHooksResponse(provider=provider, hooks=hooks, parts_updated=updated)


@router.post("/{ref}/publish", response_model=PublishResponse)
def publish_series(
    ref: str,
    body: SeriesPublishRequest,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
) -> PublishResponse:
    """Fan every eligible part out, one independent job per platform per part.

    Scheduled by default. The parts land in the backlog and leave it in
    episode order, one per slot -- which is the whole reason a series is a
    thing here and not just several uploads.
    """
    series = _load(session, ref)
    targets = body.targets or [Platform(p) for p in (series.default_targets or [])]
    if not targets:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="no targets given and the series has no default targets",
        )

    wanted = set(body.parts) if body.parts else None
    parts = [p for p in _ordered_parts(series) if wanted is None or p.part_index in wanted]
    if not parts:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="no matching parts")

    existing = {
        (job.asset_id, job.platform)
        for job in session.execute(
            select(PublishJob).where(PublishJob.asset_id.in_([p.asset_id for p in parts]))
        ).scalars()
    }

    copy = SeriesCopy.from_series(series)
    total = _effective_total(series)
    privacy = body.privacy or series.default_privacy
    state = JobState.SCHEDULED if body.schedule else JobState.PENDING

    jobs: list[PublishJob] = []
    for part in parts:
        for platform in targets:
            # Skip rather than 409 the whole request: re-running publish after
            # adding part 9 should queue part 9, not refuse because parts 1-8
            # already went out.
            if (part.asset_id, platform) in existing:
                continue
            rendered = render(
                copy,
                part_index=part.part_index,
                total=total,
                hook=part.hook,
                platform=platform,
            )
            jobs.append(
                PublishJob(
                    asset_id=part.asset_id,
                    platform=platform,
                    caption=rendered.caption,
                    title=rendered.title,
                    privacy=privacy,
                    state=state,
                )
            )

    if not jobs:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="every requested part already has jobs"
        )

    session.add_all(jobs)
    session.flush()
    responses = [JobResponse.model_validate(job) for job in jobs]
    job_ids = [job.id for job in jobs]

    if body.schedule:
        log.info("series.scheduled", series_id=series.id, jobs=len(job_ids))
        return PublishResponse(asset_id=series.id, jobs=responses)

    # Same ordering constraint as `POST /publish`: commit before the task is
    # queued, or `dispatch` is handed ids no other connection can see yet.
    session.commit()
    background.add_task(dispatch, job_ids)
    log.info("series.published", series_id=series.id, jobs=len(job_ids))
    return PublishResponse(asset_id=series.id, jobs=responses)

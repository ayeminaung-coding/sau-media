"""Slot editing, the release plan, and the tick that drains the backlog.

The cadence lives in the database, not in the n8n Cron node. n8n ticks
frequently and `POST /schedule/tick` decides whether anything is actually due,
so moving a slot is an edit in the console rather than a workflow change and a
redeploy. See `sau.schedule` for the ordering and due-time rules.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from sau.api.deps import get_session
from sau.api.schemas import (
    JobResponse,
    PublishResponse,
    SchedulePlanEntry,
    SlotResponse,
    SlotsReplace,
    TickResponse,
)
from sau.logging import get_logger
from sau.models import JobState, ScheduleSlot
from sau.queue.tasks import dispatch
from sau.schedule import due_slots, ordered_backlog, upcoming, zone

log = get_logger(__name__)

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _all_slots(session: Session) -> list[ScheduleSlot]:
    return list(
        session.execute(
            select(ScheduleSlot).order_by(ScheduleSlot.hour, ScheduleSlot.minute)
        ).scalars()
    )


@router.get("/slots", response_model=list[SlotResponse])
def list_slots(session: Session = Depends(get_session)) -> list[ScheduleSlot]:
    return _all_slots(session)


@router.put("/slots", response_model=list[SlotResponse])
def replace_slots(
    body: SlotsReplace, session: Session = Depends(get_session)
) -> list[ScheduleSlot]:
    """Replace the whole day's slots.

    A set rather than a patch: the operator is editing one daily rhythm, and
    half of a rhythm is not a state worth being able to save.

    `last_fired_on` is not carried across, so editing the slots re-arms them.
    Deliberate -- an operator who has just moved today's evening slot means
    the new time, not "already fired, see you tomorrow".
    """
    for existing in _all_slots(session):
        session.delete(existing)
    session.flush()

    slots = [
        ScheduleSlot(
            label=slot.label,
            hour=slot.hour,
            minute=slot.minute,
            timezone=slot.timezone,
            enabled=slot.enabled,
        )
        for slot in body.slots
    ]
    session.add_all(slots)
    session.flush()
    log.info("schedule.slots.replaced", count=len(slots))
    return sorted(slots, key=lambda s: (s.hour, s.minute))


@router.get("/plan", response_model=list[SchedulePlanEntry])
def release_plan(
    count: int = 12, session: Session = Depends(get_session)
) -> list[SchedulePlanEntry]:
    """Pair the next firing times with what is actually queued for them.

    The times are computed here rather than in the console because the
    arithmetic is timezone-aware, and two implementations of a DST rule will
    eventually disagree about one evening.
    """
    count = max(0, min(count, 100))
    times = upcoming(_all_slots(session), count)
    backlog = ordered_backlog(session, limit=count)

    entries: list[SchedulePlanEntry] = []
    for position, fires_at in enumerate(times):
        # More slots than backlog is the normal state; those entries are the
        # empty ones an operator fills, so they are shown rather than dropped.
        group = backlog[position] if position < len(backlog) else None
        entries.append(
            SchedulePlanEntry(
                fires_at=fires_at,
                asset_id=group.asset_id if group else None,
                series_title=group.series_title if group else "",
                part_index=group.part_index if group else None,
            )
        )
    return entries


@router.post("/tick", response_model=TickResponse)
def tick(
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    grace_minutes: int = 60,
) -> TickResponse:
    """Release one asset for every slot that has come due. Called by n8n.

    Idempotent within a slot's day: `ScheduleSlot.last_fired_on` is stamped on
    release, so ticking every minute inside the grace window still publishes
    exactly one asset per slot.
    """
    now = datetime.now(UTC)
    ready = due_slots(_all_slots(session), now, grace_minutes=grace_minutes)
    if not ready:
        return TickResponse(fired=0)

    released: list[PublishResponse] = []
    idle: list[str] = []
    job_ids: list[str] = []

    for slot in ready:
        backlog = ordered_backlog(session, limit=1)
        if not backlog:
            # Not stamped as fired: the slot stays armed for the rest of its
            # grace window, so content added a few minutes late still catches
            # the slot it was meant for instead of waiting until tomorrow.
            idle.append(slot.label or f"{slot.hour:02d}:{slot.minute:02d}")
            continue

        group = backlog[0]
        for job in group.jobs:
            job.state = JobState.PENDING
        job_ids.extend(job.id for job in group.jobs)

        slot.last_fired_on = now.astimezone(zone(slot.timezone)).date()
        released.append(
            PublishResponse(
                asset_id=group.asset_id,
                jobs=[JobResponse.model_validate(job) for job in group.jobs],
            )
        )
        log.info(
            "schedule.released",
            slot=slot.label,
            asset_id=group.asset_id,
            part=group.part_index,
            jobs=len(group.jobs),
        )

    # Same ordering constraint as `POST /publish`: the rows must be visible to
    # other connections before `dispatch` goes looking for them.
    session.commit()
    if job_ids:
        background.add_task(dispatch, job_ids)

    return TickResponse(fired=len(released), released=released, idle_slots=idle)


@router.post("/slots/reset", response_model=list[SlotResponse])
def rearm_slots(session: Session = Depends(get_session)) -> list[ScheduleSlot]:
    """Clear every slot's fired marker, so today's slots can fire again.

    The manual override for the case where a release went wrong and the
    operator wants the day's schedule to run a second time.
    """
    slots = _all_slots(session)
    if not slots:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no slots configured")
    for slot in slots:
        slot.last_fired_on = None
    session.flush()
    return slots

"""When the backlog drains, and in what order.

Two problems, both of which the previous one-asset-a-day cron sidestepped by
being too simple to hit them.

**Order.** The backlog used to be sorted by `PublishJob.created_at`. Uploading
eight parts of a series in one batch timestamps them milliseconds apart, in
whatever order the uploads happened to finish, so part 5 could publish before
part 3. A series has exactly one property that matters and that destroys it.
Series parts are therefore ordered by `SeriesPart.part_index` and nothing else.

**Cadence.** Slots live in the database (`ScheduleSlot`), not in the n8n Cron
node, so an operator can move one without a redeploy. n8n instead ticks
frequently and calls `POST /schedule/tick`; this module decides whether any
slot has come due since the last tick. That inverts the usual arrangement on
purpose: the schedule belongs to whoever is editing it, and n8n only supplies
a heartbeat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from sau.logging import get_logger
from sau.models import Asset, JobState, PublishJob, ScheduleSlot, Series, SeriesPart

log = get_logger(__name__)

#: How late a slot may fire. A tick that arrives inside this window still
#: releases; one that arrives after it skips the slot for the day rather than
#: dumping a backlog at an hour nobody chose. Wider than any sane tick
#: interval, narrower than "whenever the service came back up".
DEFAULT_GRACE_MINUTES = 60


def zone(name: str) -> ZoneInfo:
    """Resolve an IANA zone, falling back to UTC rather than raising.

    A slot with a mistyped zone should post at a surprising hour, visibly, not
    take down every other slot's release with it.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("schedule.zone.unknown", timezone=name)
        return ZoneInfo("UTC")


def is_due(
    slot: ScheduleSlot,
    now: datetime | None = None,
    *,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
) -> bool:
    """Whether `slot` should release on this tick.

    At most once per slot per local day: `last_fired_on` holds the local date
    it last went, so a tick every minute inside the grace window still
    releases exactly one asset.
    """
    if not slot.enabled:
        return False

    now = now or datetime.now(UTC)
    local = now.astimezone(zone(slot.timezone))

    if slot.last_fired_on == local.date():
        return False

    fire_at = local.replace(hour=slot.hour, minute=slot.minute, second=0, microsecond=0)
    if local < fire_at:
        return False
    return local - fire_at <= timedelta(minutes=grace_minutes)


def due_slots(
    slots: list[ScheduleSlot],
    now: datetime | None = None,
    *,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
) -> list[ScheduleSlot]:
    """Every slot ready to fire, earliest in the day first."""
    ready = [s for s in slots if is_due(s, now, grace_minutes=grace_minutes)]
    return sorted(ready, key=lambda s: (s.hour, s.minute))


def upcoming(
    slots: list[ScheduleSlot],
    count: int,
    now: datetime | None = None,
) -> list[datetime]:
    """The next `count` firing times across every enabled slot, in order.

    Computed here rather than in the console because the arithmetic is
    timezone-aware and there is no reason for two implementations of it to
    disagree about a DST boundary.
    """
    now = now or datetime.now(UTC)
    enabled = [s for s in slots if s.enabled]
    if not enabled or count <= 0:
        return []

    times: list[datetime] = []
    # Walk forward a day at a time; the window only has to be long enough to
    # collect `count` of them, and there is at least one slot per day.
    for day_offset in range(count + 1):
        for slot in enabled:
            tz = zone(slot.timezone)
            local = now.astimezone(tz) + timedelta(days=day_offset)
            fire_at = local.replace(hour=slot.hour, minute=slot.minute, second=0, microsecond=0)
            if fire_at > now.astimezone(tz):
                times.append(fire_at.astimezone(UTC))
    return sorted(times)[:count]


@dataclass
class BacklogGroup:
    """One release unit: an asset, plus the series position it holds."""

    asset_id: str
    created_at: datetime
    jobs: list[PublishJob] = field(default_factory=list)
    series_id: str | None = None
    series_title: str = ""
    part_index: int | None = None
    #: What the whole group sorts by. A series' parts share the first element
    #: so they stay contiguous, and separate on the second so they stay in
    #: episode order.
    sort_key: tuple[datetime, int] = field(default=(datetime.min.replace(tzinfo=UTC), 0))


def ordered_backlog(session: Session, limit: int = 50) -> list[BacklogGroup]:
    """The backlog in the exact order it will publish in.

    One function, used by both the console's preview and the tick that
    actually releases, because a preview that disagrees with the release order
    is worse than no preview.
    """
    rows = list(
        session.execute(
            select(PublishJob)
            .where(PublishJob.state == JobState.SCHEDULED)
            .options(selectinload(PublishJob.asset).selectinload(Asset.part))
            .order_by(PublishJob.created_at)
        ).scalars()
    )

    groups: dict[str, BacklogGroup] = {}
    for job in rows:
        group = groups.get(job.asset_id)
        if group is None:
            part = job.asset.part if job.asset else None
            group = BacklogGroup(asset_id=job.asset_id, created_at=job.created_at)
            if part is not None:
                group.series_id = part.series_id
                group.part_index = part.part_index
                group.series_title = _series_title(session, part)
            groups[job.asset_id] = group
        group.jobs.append(job)

    return order_groups(list(groups.values()))[:limit]


def order_groups(groups: list[BacklogGroup]) -> list[BacklogGroup]:
    """Put backlog groups in release order.

    A series is placed by when its earliest part was queued, then held
    together and ordered internally by episode number -- so uploading part 7
    late does not send it to the back of the queue behind unrelated assets,
    and a batch upload cannot interleave episodes. A standalone asset keeps
    the plain oldest-first behaviour it has always had.

    Split out from the query so the rule can be tested without a database,
    which is where the risk actually is.
    """
    earliest: dict[str, datetime] = {}
    for group in groups:
        if group.series_id:
            current = earliest.get(group.series_id)
            if current is None or group.created_at < current:
                earliest[group.series_id] = group.created_at

    for group in groups:
        if group.series_id:
            group.sort_key = (earliest[group.series_id], group.part_index or 0)
        else:
            group.sort_key = (group.created_at, 0)

    return sorted(groups, key=lambda g: g.sort_key)


def _series_title(session: Session, part: SeriesPart) -> str:
    series = session.get(Series, part.series_id)
    if series is None:
        return ""
    return series.title_local or series.title_en or series.slug


#: What a fresh install starts with. Three releases a day, which is the rhythm
#: a serialised show is usually cut for. Not authoritative -- the moment the
#: operator edits the slots in the console these are irrelevant, which is the
#: entire reason they live in a table and not in the environment.
DEFAULT_SLOTS: tuple[tuple[str, int, int], ...] = (
    ("Lunch", 12, 0),
    ("Evening", 18, 0),
    ("Night", 21, 0),
)
DEFAULT_TIMEZONE = "Asia/Bangkok"


def ensure_default_slots(session: Session, timezone: str = DEFAULT_TIMEZONE) -> list[ScheduleSlot]:
    """Seed the default slots, but only into an empty table.

    Never overwrites: an operator who deliberately runs a single slot must not
    have two more reinstated under them on the next deploy.
    """
    existing = list(session.execute(select(ScheduleSlot)).scalars())
    if existing:
        return existing

    slots = [
        ScheduleSlot(label=label, hour=hour, minute=minute, timezone=timezone)
        for label, hour, minute in DEFAULT_SLOTS
    ]
    session.add_all(slots)
    session.flush()
    log.info("schedule.slots.seeded", count=len(slots))
    return slots

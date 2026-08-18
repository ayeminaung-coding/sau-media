"""Database models.

The schema is deliberately fan-out shaped: one `Asset` (the source video) has
one `PublishJob` per target platform. Jobs never share state, so a TikTok
failure can be retried without touching a completed Facebook upload.

`Series` sits above that: many assets that must be released in a fixed order,
carrying the caption material an episode is rendered from. It changes nothing
about the fan-out -- a series part still becomes ordinary independent jobs.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Platform(enum.StrEnum):
    FACEBOOK_REEL = "facebook_reel"
    FACEBOOK_VIDEO = "facebook_video"
    TIKTOK = "tiktok"


#: Longest caption each platform accepts. Mirrors the same table in
#: `console/src/domain/platforms.ts`; a value changed in one belongs in the other.
CAPTION_LIMITS: dict[Platform, int] = {
    Platform.TIKTOK: 2200,
    Platform.FACEBOOK_REEL: 2200,
    Platform.FACEBOOK_VIDEO: 5000,
}

#: Longest title each platform accepts. Zero means the platform has no title
#: field at all and drops whatever is sent -- Reels are that case.
TITLE_LIMITS: dict[Platform, int] = {
    Platform.TIKTOK: 150,
    Platform.FACEBOOK_REEL: 0,
    Platform.FACEBOOK_VIDEO: 255,
}


class JobState(enum.StrEnum):
    """Lifecycle of a single platform publish.

    SCHEDULED -> PENDING -> TRANSCODING -> UPLOADING -> PROCESSING -> PUBLISHED
                                                                   \\-> FAILED
    PROCESSING means the bytes are delivered and the platform is encoding;
    it is polled, not pushed.

    SCHEDULED is the backlog: the job exists with its caption and targets
    settled, but was never put on a queue. It leaves that state only when
    something releases it — the daily n8n cron, or a human in the console.
    """

    SCHEDULED = "scheduled"
    PENDING = "pending"
    TRANSCODING = "transcoding"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"


TERMINAL_STATES = frozenset({JobState.PUBLISHED, JobState.FAILED})


class Asset(Base):
    """A source video uploaded to object storage, before any platform work."""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    width: Mapped[int | None] = mapped_column(Integer, default=None)
    height: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    jobs: Mapped[list[PublishJob]] = relationship(back_populates="asset")
    renditions: Mapped[list[Rendition]] = relationship(back_populates="asset")
    #: Set only for an asset that belongs to a series. Ordinary one-off
    #: uploads leave it None and behave exactly as they did before.
    part: Mapped[SeriesPart | None] = relationship(back_populates="asset", uselist=False)


class Rendition(Base):
    """A transcoded copy of an asset, shaped for one platform's constraints."""

    __tablename__ = "renditions"
    __table_args__ = (UniqueConstraint("asset_id", "platform", name="uq_rendition_asset_platform"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform, native_enum=False))
    storage_key: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    asset: Mapped[Asset] = relationship(back_populates="renditions")


class PublishJob(Base):
    """One platform's publish attempt for one asset."""

    __tablename__ = "publish_jobs"
    __table_args__ = (
        UniqueConstraint("asset_id", "platform", name="uq_job_asset_platform"),
        Index("ix_job_state_platform", "state", "platform"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform, native_enum=False))
    state: Mapped[JobState] = mapped_column(
        Enum(JobState, native_enum=False), default=JobState.PENDING
    )

    caption: Mapped[str] = mapped_column(Text, default="")
    #: Optional headline. TikTok shows it as the post title; Facebook feed
    #: video has a distinct title field. Reels have none and ignore it.
    title: Mapped[str] = mapped_column(String(255), default="")
    privacy: Mapped[str] = mapped_column(String(64), default="PUBLIC_TO_EVERYONE")

    #: Platform-side identifier: FB video id, or TikTok publish_id.
    external_id: Mapped[str | None] = mapped_column(String(128), default=None)
    #: Permalink, once the platform exposes one.
    external_url: Mapped[str | None] = mapped_column(String(512), default=None)

    #: Byte offset already accepted by the platform, for resumed uploads.
    uploaded_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    asset: Mapped[Asset] = relationship(back_populates="jobs")

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES


class OAuthToken(Base):
    """Rotating platform credentials.

    Only TikTok genuinely needs this: its access tokens expire in ~24h. A
    long-lived Facebook Page token is stored here too so both platforms share
    one refresh code path.
    """

    __tablename__ = "oauth_tokens"

    platform: Mapped[str] = mapped_column(String(32), primary_key=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    def expires_within(self, seconds: int) -> bool:
        if self.expires_at is None:
            return False
        return (self.expires_at - _now()).total_seconds() < seconds


class Series(Base):
    """A serialised show: many assets that must go out in a fixed order.

    Everything an episode's caption is built from lives here rather than being
    retyped per part, because for a series the caption is almost entirely
    structural -- title, episode number, a pointer to the next part, a fixed
    hashtag set -- and only one line genuinely varies. That line is
    `SeriesPart.hook`.

    The templates are stored, not hard-coded, so the Chinese copy an operator
    writes stays in their hands and never becomes a string literal in here.
    """

    __tablename__ = "series"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(128), unique=True)
    #: The title as it appears in the caption -- Burmese, Chinese, whatever the
    #: audience reads. Renders as {series}.
    title_local: Mapped[str] = mapped_column(String(255), default="")
    title_en: Mapped[str] = mapped_column(String(255), default="")

    #: Plot summary for the whole series. Never published -- it is the context
    #: the caption generator is given, and the operator's own notes.
    synopsis: Mapped[str] = mapped_column(Text, default="")

    #: What language the hooks are drafted in. Per series, not global: the
    #: source animation and the audience reading the caption are routinely not
    #: the same language.
    language: Mapped[str] = mapped_column(String(64), default="Burmese")

    #: One real hook, in the operator's own voice, shown to the model as the
    #: house style. This is the single biggest lever on output quality --
    #: an example of the wanted voice, length and punctuation beats any amount
    #: of instruction about them, especially in a language the model has seen
    #: less of.
    style_example: Mapped[str] = mapped_column(Text, default="")

    #: Declared episode count. None means open-ended, and the count of
    #: registered parts stands in wherever `{total}` is rendered.
    total_parts: Mapped[int | None] = mapped_column(Integer, default=None)

    caption_template: Mapped[str] = mapped_column(Text, default="")
    title_template: Mapped[str] = mapped_column(String(512), default="")
    #: Rendered into `{next_teaser}`, and left empty on the final part so the
    #: last episode does not promise one that will never arrive.
    next_teaser_template: Mapped[str] = mapped_column(String(512), default="")

    #: Hashtag block per platform, keyed by `Platform` value. Per-platform
    #: because the tags that work on TikTok are not the ones that work on a
    #: Facebook feed video, and the caption limits differ too.
    hashtags: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    #: Platforms a new part is published to unless the operator changes it.
    default_targets: Mapped[list[str]] = mapped_column(JSON, default=list)
    default_privacy: Mapped[str] = mapped_column(String(64), default="PUBLIC_TO_EVERYONE")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    parts: Mapped[list[SeriesPart]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )


class SeriesPart(Base):
    """One episode: an asset plus its position in the series.

    `part_index` is parsed from the filename (`part3_something.mp4`) and is the
    only thing release order is ever taken from. Ordering by `created_at` is
    wrong here -- a batch upload timestamps eight parts milliseconds apart, and
    part 5 going out before part 3 destroys the one property a series has.
    """

    __tablename__ = "series_parts"
    __table_args__ = (
        UniqueConstraint("series_id", "part_index", name="uq_part_series_index"),
        Index("ix_part_series_order", "series_id", "part_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), unique=True, index=True
    )
    part_index: Mapped[int] = mapped_column(Integer)

    #: The one line that actually differs between episodes. Drafted by the
    #: caption generator or typed by the operator; always editable.
    hook: Mapped[str] = mapped_column(Text, default="")
    #: The name the file arrived under, kept so a part can be matched back to
    #: whatever produced it.
    source_filename: Mapped[str] = mapped_column(String(255), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    series: Mapped[Series] = relationship(back_populates="parts")
    asset: Mapped[Asset] = relationship(back_populates="part")


class ScheduleSlot(Base):
    """One posting time of day, editable at runtime.

    These live in the database rather than in the environment or the n8n Cron
    node because the posting rhythm is something an operator retunes, and a
    redeploy is too high a price for moving a slot by an hour. n8n ticks often
    and this table decides whether anything is actually due; see
    `sau.schedule`.
    """

    __tablename__ = "schedule_slots"
    __table_args__ = (Index("ix_slot_order", "enabled", "hour", "minute"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    label: Mapped[str] = mapped_column(String(64), default="")
    hour: Mapped[int] = mapped_column(Integer)
    minute: Mapped[int] = mapped_column(Integer, default=0)
    #: IANA zone name. Stored per slot so a schedule can straddle regions
    #: without the whole service having to agree on one local time.
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Bangkok")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    #: Local date this slot last released on. The guard against fanning out
    #: repeatedly while the tick keeps arriving inside the same grace window --
    #: at-most-once per slot per local day, whatever the tick interval is.
    last_fired_on: Mapped[date | None] = mapped_column(Date, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

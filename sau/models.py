"""Database models.

The schema is deliberately fan-out shaped: one `Asset` (the source video) has
one `PublishJob` per target platform. Jobs never share state, so a TikTok
failure can be retried without touching a completed Facebook upload.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
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

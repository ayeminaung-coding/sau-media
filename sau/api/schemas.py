"""Request and response models for the HTTP API."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from sau.captions.generate import DEFAULT_HOOK_MAX_CHARS
from sau.captions.template import (
    DEFAULT_CAPTION_TEMPLATE,
    DEFAULT_NEXT_TEASER_TEMPLATE,
    DEFAULT_TITLE_TEMPLATE,
)
from sau.models import JobState, Platform


class UploadUrlRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    #: Signed into the PUT URL, so the uploader must send it back verbatim.
    content_type: str = Field(default="video/mp4", min_length=1, max_length=128)


class UploadUrlResponse(BaseModel):
    storage_key: str
    upload_url: str
    expires_seconds: int


class RegisterAssetRequest(BaseModel):
    storage_key: str = Field(min_length=1, max_length=512)


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    storage_key: str
    size_bytes: int
    duration_seconds: float | None
    width: int | None
    height: int | None
    created_at: datetime


class PublishTarget(BaseModel):
    platform: Platform
    caption: str = Field(default="", max_length=5000)
    title: str = Field(default="", max_length=255)
    privacy: str = Field(default="PUBLIC_TO_EVERYONE", max_length=64)


class PublishRequestBody(BaseModel):
    asset_id: str
    targets: list[PublishTarget] = Field(min_length=1)
    #: Park the jobs in the backlog instead of queueing them now. They publish
    #: when `POST /assets/{id}/release` is called, normally by the daily cron.
    schedule: bool = False


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    asset_id: str
    platform: Platform
    state: JobState
    caption: str
    title: str
    external_id: str | None
    external_url: str | None
    uploaded_bytes: int
    attempts: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class PublishResponse(BaseModel):
    asset_id: str
    jobs: list[JobResponse]


class BacklogEntry(BaseModel):
    """One scheduled asset and every platform waiting to go out with it."""

    asset_id: str
    created_at: datetime
    jobs: list[JobResponse]
    #: Set when the asset is an episode. The backlog is ordered by these, not
    #: by upload time, so a batch-uploaded series cannot publish out of order.
    series_id: str | None = None
    series_title: str = ""
    part_index: int | None = None


# ---- Series -------------------------------------------------------------
#
# A series is caption material plus an ordering. Nothing here changes the
# fan-out: publishing a part still creates one independent job per platform,
# exactly as a one-off upload does.


class SeriesBase(BaseModel):
    #: The title as it appears in the caption. Renders as {series}.
    title_local: str = Field(default="", max_length=255)
    title_en: str = Field(default="", max_length=255)
    #: Never published. It is the context the caption generator is given.
    synopsis: str = Field(default="", max_length=8000)
    #: What the hooks are drafted in. Per series, because the source animation
    #: and the audience reading the caption are routinely different languages.
    language: str = Field(default="Burmese", max_length=64)
    #: One real caption in the operator's own voice, shown to the model as the
    #: house style. The single biggest lever on output quality.
    style_example: str = Field(default="", max_length=4000)
    #: None means open-ended; the count of registered parts stands in for it.
    total_parts: int | None = Field(default=None, ge=1, le=9999)
    caption_template: str = Field(default=DEFAULT_CAPTION_TEMPLATE, max_length=5000)
    title_template: str = Field(default=DEFAULT_TITLE_TEMPLATE, max_length=512)
    next_teaser_template: str = Field(default=DEFAULT_NEXT_TEASER_TEMPLATE, max_length=512)
    #: Keyed by `Platform` value; the tags that work on TikTok are not the
    #: ones that work on a Facebook feed video.
    hashtags: dict[str, str] = Field(default_factory=dict)
    default_targets: list[Platform] = Field(default_factory=list)
    default_privacy: str = Field(default="PUBLIC_TO_EVERYONE", max_length=64)


class SeriesCreate(SeriesBase):
    slug: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9\-_]*$")


class SeriesUpdate(BaseModel):
    """Every field optional: the console saves one card at a time."""

    title_local: str | None = Field(default=None, max_length=255)
    title_en: str | None = Field(default=None, max_length=255)
    synopsis: str | None = Field(default=None, max_length=8000)
    language: str | None = Field(default=None, max_length=64)
    style_example: str | None = Field(default=None, max_length=4000)
    total_parts: int | None = Field(default=None, ge=1, le=9999)
    caption_template: str | None = Field(default=None, max_length=5000)
    title_template: str | None = Field(default=None, max_length=512)
    next_teaser_template: str | None = Field(default=None, max_length=512)
    hashtags: dict[str, str] | None = None
    default_targets: list[Platform] | None = None
    default_privacy: str | None = Field(default=None, max_length=64)


class CaptionPreview(BaseModel):
    """One part rendered for one platform, exactly as it would publish."""

    platform: Platform
    caption: str
    title: str
    caption_limit: int
    title_limit: int


class SeriesPartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    series_id: str
    asset_id: str
    part_index: int
    hook: str
    source_filename: str
    duration_seconds: float | None = None
    #: State of this part's publish jobs, if it has any yet.
    jobs: list[JobResponse] = Field(default_factory=list)
    created_at: datetime


class SeriesResponse(SeriesBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    created_at: datetime
    #: Registered episodes, in episode order — never upload order.
    parts: list[SeriesPartResponse] = Field(default_factory=list)
    #: Gaps in the numbering. A missing episode means a file was not uploaded,
    #: and the operator wants that before the schedule is built around it.
    missing_parts: list[int] = Field(default_factory=list)
    #: `total_parts` if declared, else how many parts are registered. This is
    #: what `{total}` renders as.
    effective_total: int = 0


class RegisterPartRequest(BaseModel):
    """Attach an already-uploaded object to a series as one episode."""

    storage_key: str = Field(min_length=1, max_length=512)
    #: The original name, which is where the episode number comes from.
    filename: str = Field(min_length=1, max_length=255)
    #: Override the number parsed from the filename. For the file that was
    #: named wrongly and is not worth re-uploading.
    part_index: int | None = Field(default=None, ge=1, le=9999)
    hook: str = Field(default="", max_length=500)


class PartUpdate(BaseModel):
    hook: str | None = Field(default=None, max_length=500)
    part_index: int | None = Field(default=None, ge=1, le=9999)


class GenerateHooksRequest(BaseModel):
    """Draft the one line per episode that actually varies."""

    #: Overrides the series' own language for this run only.
    language: str | None = Field(default=None, max_length=64)
    max_chars: int = Field(default=DEFAULT_HOOK_MAX_CHARS, ge=20, le=2000)
    #: False leaves hooks that already have text alone and shows them to the
    #: model as settled, so a re-run extends the arc rather than rewriting it.
    overwrite: bool = False


class GenerateHooksResponse(BaseModel):
    #: Which provider actually served — the first configured one that answered.
    provider: str
    hooks: dict[int, str]
    parts_updated: int


class SeriesPublishRequest(BaseModel):
    """Fan every registered part out, in episode order."""

    targets: list[Platform] | None = None
    privacy: str | None = Field(default=None, max_length=64)
    #: Only these episodes; omit for all of them that have no jobs yet.
    parts: list[int] | None = None
    #: Default true: a series is the case the drip schedule exists for.
    schedule: bool = True


# ---- Schedule slots -----------------------------------------------------


class SlotBase(BaseModel):
    label: str = Field(default="", max_length=64)
    hour: int = Field(ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    timezone: str = Field(default="Asia/Bangkok", max_length=64)
    enabled: bool = True


class SlotResponse(SlotBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    last_fired_on: date | None


class SlotsReplace(BaseModel):
    """The whole day's slots, replacing whatever is stored.

    Sent as a set rather than patched one at a time: the operator is editing a
    daily rhythm, and a half-applied rhythm is not a state worth having.
    """

    slots: list[SlotBase] = Field(max_length=24)


class SchedulePlanEntry(BaseModel):
    """One upcoming release: when it fires, and what is due to go out."""

    fires_at: datetime
    asset_id: str | None = None
    series_title: str = ""
    part_index: int | None = None


class TickResponse(BaseModel):
    """What `POST /schedule/tick` did, so n8n can log something useful."""

    fired: int
    released: list[PublishResponse] = Field(default_factory=list)
    #: Slots that came due with an empty backlog. Not an error.
    idle_slots: list[str] = Field(default_factory=list)

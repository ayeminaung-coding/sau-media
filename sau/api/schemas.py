"""Request and response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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

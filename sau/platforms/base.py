"""The contract every platform adapter implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar

from sau.models import JobState, Platform


@dataclass(frozen=True)
class PublishRequest:
    """Everything an adapter needs to publish one rendition."""

    job_id: str
    #: Object storage key of the platform-specific rendition.
    storage_key: str
    size_bytes: int
    caption: str
    privacy: str
    #: Bytes the platform has already accepted, for a resumed upload.
    resume_offset: int = 0
    #: Called after each accepted chunk so the caller can persist progress.
    on_progress: Callable[[int], None] = field(default=lambda _: None, compare=False)


@dataclass(frozen=True)
class PublishResult:
    """Outcome of handing the bytes over."""

    external_id: str
    #: PROCESSING when the platform is still encoding, PUBLISHED when live.
    state: JobState = JobState.PROCESSING
    external_url: str | None = None


@dataclass(frozen=True)
class StatusResult:
    """Outcome of polling a previously started publish."""

    state: JobState
    external_url: str | None = None
    error: str | None = None


class Publisher(ABC):
    """Adapter for a single publishing target."""

    platform: ClassVar[Platform]

    @abstractmethod
    def publish(self, request: PublishRequest) -> PublishResult:
        """Transfer the rendition and start the platform-side publish."""

    @abstractmethod
    def check_status(self, external_id: str) -> StatusResult:
        """Poll a publish started by `publish`."""

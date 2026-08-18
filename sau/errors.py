"""Error taxonomy shared by every platform adapter.

The only distinction the queue cares about is `retryable`: a 429 or a 502 gets
another attempt, a rejected caption or a revoked token does not.
"""

from __future__ import annotations

from typing import Any


class SauError(Exception):
    """Base class for all application errors."""


class PlatformError(SauError):
    """A platform API returned something we could not use."""

    def __init__(
        self,
        message: str,
        *,
        platform: str,
        retryable: bool = False,
        status_code: int | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.platform = platform
        self.retryable = retryable
        self.status_code = status_code
        self.payload = payload

    def __str__(self) -> str:
        base = super().__str__()
        return f"[{self.platform}] {base}" + (
            f" (HTTP {self.status_code})" if self.status_code else ""
        )


class AuthError(PlatformError):
    """Credentials are missing, expired beyond refresh, or lack a scope."""

    def __init__(self, message: str, *, platform: str, **kwargs: Any) -> None:
        kwargs.pop("retryable", None)
        super().__init__(message, platform=platform, retryable=False, **kwargs)


class UploadError(PlatformError):
    """A chunk or session failed mid-transfer."""


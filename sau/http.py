"""HTTP client with uniform retry behaviour for platform APIs."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx

from sau.errors import PlatformError
from sau.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")

#: Long read timeout: upload chunks and Graph publish calls are slow.
DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=300.0, pool=10.0)

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def build_client(**kwargs: Any) -> httpx.Client:
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    kwargs.setdefault("follow_redirects", True)
    return httpx.Client(**kwargs)


def is_retryable(response: httpx.Response) -> bool:
    return response.status_code in RETRYABLE_STATUS


def _backoff(attempt: int, base: float, cap: float) -> float:
    """Exponential backoff with full jitter."""
    return random.uniform(0, min(cap, base * (2**attempt)))


def with_retries(
    operation: Callable[[], T],
    *,
    attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    label: str = "request",
) -> T:
    """Run `operation`, retrying only errors marked retryable.

    `operation` must raise `PlatformError` (or `httpx.TransportError`) to
    signal failure; anything else propagates untouched.
    """
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            return operation()
        except PlatformError as exc:
            if not exc.retryable:
                raise
            last_error = exc
        except httpx.TransportError as exc:
            last_error = exc

        if attempt < attempts - 1:
            delay = _backoff(attempt, base_delay, max_delay)
            log.warning(
                "http.retry", label=label, attempt=attempt + 1, delay=round(delay, 2),
                error=str(last_error),
            )
            time.sleep(delay)

    if last_error is None:  # attempts < 1; the loop never ran
        raise ValueError(f"{label}: attempts must be at least 1")
    raise last_error


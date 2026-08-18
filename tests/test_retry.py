"""`with_retries` must retry only what is marked retryable."""

import httpx
import pytest

from sau.errors import PlatformError
from sau.http import with_retries


def test_returns_immediately_on_success():
    calls = []

    def operation():
        calls.append(1)
        return "done"

    assert with_retries(operation, attempts=3, base_delay=0) == "done"
    assert len(calls) == 1


def test_non_retryable_error_is_not_retried():
    calls = []

    def operation():
        calls.append(1)
        raise PlatformError("rejected", platform="tiktok", retryable=False)

    with pytest.raises(PlatformError):
        with_retries(operation, attempts=5, base_delay=0)
    assert len(calls) == 1


def test_retryable_error_succeeds_on_a_later_attempt():
    calls = []

    def operation():
        calls.append(1)
        if len(calls) < 3:
            raise PlatformError("throttled", platform="tiktok", retryable=True)
        return "ok"

    assert with_retries(operation, attempts=5, base_delay=0) == "ok"
    assert len(calls) == 3


def test_transport_errors_are_retried_then_surfaced():
    calls = []

    def operation():
        calls.append(1)
        raise httpx.ConnectError("connection reset")

    with pytest.raises(httpx.ConnectError):
        with_retries(operation, attempts=3, base_delay=0)
    assert len(calls) == 3

"""Both platforms hide failures inside HTTP 200 bodies; these guard that."""

import httpx
import pytest

from sau.errors import AuthError, PlatformError
from sau.platforms.facebook.client import _unwrap as fb_unwrap
from sau.platforms.tiktok.client import _unwrap as tt_unwrap


def _response(payload, status_code=200):
    return httpx.Response(
        status_code=status_code, json=payload, request=httpx.Request("POST", "https://example.test")
    )


class TestTikTok:
    def test_ok_envelope_returns_data(self):
        response = _response({"data": {"publish_id": "p1"}, "error": {"code": "ok"}})
        assert tt_unwrap(response, operation="init")["publish_id"] == "p1"

    def test_error_code_on_http_200_still_raises(self):
        response = _response({"data": {}, "error": {"code": "invalid_param", "message": "bad"}})
        with pytest.raises(PlatformError) as exc:
            tt_unwrap(response, operation="init")
        assert exc.value.retryable is False

    def test_rate_limit_is_retryable(self):
        response = _response({"error": {"code": "rate_limit_exceeded", "message": "slow down"}})
        with pytest.raises(PlatformError) as exc:
            tt_unwrap(response, operation="init")
        assert exc.value.retryable is True

    def test_invalid_token_raises_auth_error(self):
        response = _response({"error": {"code": "access_token_invalid", "message": "nope"}})
        with pytest.raises(AuthError):
            tt_unwrap(response, operation="init")


class TestFacebook:
    def test_plain_body_is_returned(self):
        assert fb_unwrap(_response({"video_id": "v1"}), operation="start")["video_id"] == "v1"

    def test_rate_limit_code_is_retryable(self):
        response = _response({"error": {"code": 4, "message": "throttled"}}, status_code=400)
        with pytest.raises(PlatformError) as exc:
            fb_unwrap(response, operation="start")
        assert exc.value.retryable is True

    def test_expired_token_raises_auth_error(self):
        response = _response({"error": {"code": 190, "message": "expired"}}, status_code=400)
        with pytest.raises(AuthError):
            fb_unwrap(response, operation="start")

    def test_non_json_body_is_reported_not_swallowed(self):
        response = httpx.Response(
            502, text="<html>bad gateway</html>", request=httpx.Request("POST", "https://x.test")
        )
        with pytest.raises(PlatformError) as exc:
            fb_unwrap(response, operation="start")
        assert exc.value.retryable is True

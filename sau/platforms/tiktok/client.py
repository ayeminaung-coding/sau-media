"""Thin transport layer over the TikTok Content Posting API.

Every TikTok response carries an `error` envelope with `code == "ok"` on
success, including on HTTP 200. Checking the HTTP status alone silently
accepts failures, so all decoding funnels through `_unwrap`.
"""

from __future__ import annotations

from typing import Any

import httpx

from sau.config import get_settings
from sau.errors import AuthError, PlatformError
from sau.http import build_client, is_retryable
from sau.logging import get_logger
from sau.tokens import get_access_token

log = get_logger(__name__)

API_BASE = "https://open.tiktokapis.com/v2"
PLATFORM = "tiktok"

#: Error codes that mean "try again", as opposed to a rejected request.
RETRYABLE_CODES = frozenset({"rate_limit_exceeded", "internal_error", "server_error"})

#: Codes that mean the credential itself is bad; retrying cannot help.
AUTH_CODES = frozenset({"access_token_invalid", "scope_not_authorized", "scope_permission_missed"})


def refresh_access_token(refresh_token: str) -> tuple[str, str, int]:
    """Exchange a refresh token for a new access token.

    TikTok access tokens live ~24h and the refresh token is rotated on every
    use, so the new one must be persisted alongside the access token.
    """
    settings = get_settings()
    with build_client() as client:
        response = client.post(
            f"{API_BASE}/oauth/token/",
            data={
                "client_key": settings.tiktok_client_key,
                "client_secret": settings.tiktok_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    payload = response.json()
    if response.status_code != 200 or "access_token" not in payload:
        raise AuthError(
            f"token refresh failed: {payload.get('error_description') or payload}",
            platform=PLATFORM,
            status_code=response.status_code,
            payload=payload,
        )

    return (
        str(payload["access_token"]),
        str(payload["refresh_token"]),
        int(payload["expires_in"]),
    )


def _unwrap(response: httpx.Response, *, operation: str) -> dict[str, Any]:
    """Return `data` from a TikTok envelope, raising on any error code."""
    try:
        payload = response.json()
    except ValueError:
        raise PlatformError(
            f"{operation}: non-JSON response",
            platform=PLATFORM,
            retryable=is_retryable(response),
            status_code=response.status_code,
            payload=response.text[:500],
        ) from None

    error = payload.get("error") or {}
    code = error.get("code", "ok")

    if code == "ok" and response.is_success:
        return dict(payload.get("data") or {})

    message = f"{operation}: {code} - {error.get('message', response.text[:300])}"
    if code in AUTH_CODES:
        raise AuthError(
            message, platform=PLATFORM, status_code=response.status_code, payload=payload
        )

    raise PlatformError(
        message,
        platform=PLATFORM,
        retryable=code in RETRYABLE_CODES or is_retryable(response),
        status_code=response.status_code,
        payload=payload,
    )


class TikTokClient:
    """Authenticated session against the Content Posting API."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or build_client()
        self._owns_client = client is None

    def __enter__(self) -> TikTokClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    @property
    def _headers(self) -> dict[str, str]:
        token = get_access_token(PLATFORM, refresh=refresh_access_token)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def _post(self, path: str, body: dict[str, Any], *, operation: str) -> dict[str, Any]:
        response = self._client.post(f"{API_BASE}{path}", json=body, headers=self._headers)
        return _unwrap(response, operation=operation)

    def query_creator_info(self) -> dict[str, Any]:
        """Fetch posting constraints for the authorised creator.

        Required before a direct post: it reports which privacy levels the
        account allows and the maximum duration it accepts.
        """
        return self._post(
            "/post/publish/creator_info/query/", {}, operation="creator_info.query"
        )

    def init_pull_from_url(self, post_info: dict[str, Any], video_url: str) -> dict[str, Any]:
        """Start a publish where TikTok downloads the video itself.

        The URL's domain prefix must be verified in the developer portal.
        """
        return self._post(
            "/post/publish/video/init/",
            {
                "post_info": post_info,
                "source_info": {"source": "PULL_FROM_URL", "video_url": video_url},
            },
            operation="publish.init.pull",
        )

    def init_file_upload(
        self, post_info: dict[str, Any], video_size: int, chunk_size: int, total_chunks: int
    ) -> dict[str, Any]:
        """Start a publish we feed chunk by chunk. Returns an `upload_url`."""
        return self._post(
            "/post/publish/video/init/",
            {
                "post_info": post_info,
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": chunk_size,
                    "total_chunk_count": total_chunks,
                },
            },
            operation="publish.init.upload",
        )

    def upload_chunk(
        self, upload_url: str, data: bytes, offset: int, total_size: int
    ) -> None:
        """PUT one byte range to the session's upload URL."""
        last_byte = offset + len(data) - 1
        response = self._client.put(
            upload_url,
            content=data,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(len(data)),
                "Content-Range": f"bytes {offset}-{last_byte}/{total_size}",
            },
        )
        # Chunk PUTs answer with bare HTTP statuses, not the JSON envelope.
        if not response.is_success:
            raise PlatformError(
                f"chunk upload failed at offset {offset}",
                platform=PLATFORM,
                retryable=is_retryable(response),
                status_code=response.status_code,
                payload=response.text[:300],
            )

    def fetch_status(self, publish_id: str) -> dict[str, Any]:
        return self._post(
            "/post/publish/status/fetch/",
            {"publish_id": publish_id},
            operation="publish.status",
        )

"""Transport layer over the Facebook Graph API.

Two upload protocols live here because Meta ships two:

* Reels use a *session* on ``rupload.facebook.com``: start a session on the
  Graph edge, push bytes at an offset, then finish. Resume is real — the
  accepted byte count is readable from the video's status.
* Feed videos use the older *phased* upload on the ``/videos`` edge, where
  each transfer response dictates the next ``start_offset``.

Both edges also accept a ``file_url``, which makes Meta fetch the file itself.
That path is preferred whenever the bucket has a public domain.
"""

from __future__ import annotations

from typing import Any

import httpx

from sau.config import get_settings
from sau.errors import AuthError, PlatformError, UploadError
from sau.http import build_client, is_retryable
from sau.logging import get_logger
from sau.tokens import get_access_token

log = get_logger(__name__)

PLATFORM = "facebook"

#: Graph error codes worth another attempt: transient backend faults and the
#: several flavours of rate limiting.
RETRYABLE_CODES = frozenset({1, 2, 4, 17, 32, 341, 613})

#: Codes meaning the token is invalid or a permission is missing.
AUTH_CODES = frozenset({102, 190, 200, 10, 803})


def _page_token() -> str:
    """Return the Page access token.

    A long-lived Page token derived from a long-lived User token does not
    expire, so no refresh callback is supplied. If it is ever revoked the
    Graph API answers with code 190 and the job fails non-retryably.
    """
    return get_access_token(PLATFORM)


def _unwrap(response: httpx.Response, *, operation: str) -> dict[str, Any]:
    """Return the decoded body, converting Graph errors into exceptions."""
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

    if response.is_success and "error" not in payload:
        return dict(payload)

    error = payload.get("error") or {}
    code = int(error.get("code", 0))
    message = f"{operation}: {error.get('message', response.text[:300])} (code {code})"

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


class FacebookClient:
    """Authenticated session against a single Facebook Page."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self._settings = settings
        self._page_id = settings.facebook_page_id
        self._client = client or build_client()
        self._owns_client = client is None

    def __enter__(self) -> FacebookClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _graph_post(self, path: str, data: dict[str, Any], *, operation: str) -> dict[str, Any]:
        body = {**data, "access_token": _page_token()}
        response = self._client.post(f"{self._settings.graph_base_url}/{path}", data=body)
        return _unwrap(response, operation=operation)

    def _graph_get(self, path: str, params: dict[str, Any], *, operation: str) -> dict[str, Any]:
        query = {**params, "access_token": _page_token()}
        response = self._client.get(f"{self._settings.graph_base_url}/{path}", params=query)
        return _unwrap(response, operation=operation)

    # -- Reels: session-based resumable upload ----------------------------

    def start_reel_session(self) -> tuple[str, str]:
        """Open a Reels upload session. Returns `(video_id, upload_url)`."""
        data = self._graph_post(
            f"{self._page_id}/video_reels",
            {"upload_phase": "start"},
            operation="reel.start",
        )
        return str(data["video_id"]), str(data["upload_url"])

    def upload_reel_bytes(
        self, upload_url: str, data: bytes, offset: int, file_size: int
    ) -> None:
        """Push a byte range into an open Reels session."""
        response = self._client.post(
            upload_url,
            content=data,
            headers={
                "Authorization": f"OAuth {_page_token()}",
                "offset": str(offset),
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream",
            },
        )
        if not response.is_success:
            raise UploadError(
                f"reel byte range rejected at offset {offset}",
                platform=PLATFORM,
                retryable=is_retryable(response),
                status_code=response.status_code,
                payload=response.text[:300],
            )

    def upload_reel_from_url(self, upload_url: str, file_url: str) -> None:
        """Hand Meta a URL and let it fetch the Reel itself."""
        response = self._client.post(
            upload_url,
            headers={"Authorization": f"OAuth {_page_token()}", "file_url": file_url},
        )
        if not response.is_success:
            raise UploadError(
                "reel hosted upload rejected",
                platform=PLATFORM,
                retryable=is_retryable(response),
                status_code=response.status_code,
                payload=response.text[:300],
            )

    def finish_reel(self, video_id: str, description: str) -> None:
        """Publish a Reel whose bytes have been fully transferred."""
        self._graph_post(
            f"{self._page_id}/video_reels",
            {
                "upload_phase": "finish",
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": description,
            },
            operation="reel.finish",
        )

    # -- Feed video: phased chunked upload --------------------------------

    def start_video_session(self, file_size: int) -> dict[str, Any]:
        """Open a phased upload. Returns session id and first offset window."""
        return self._graph_post(
            f"{self._page_id}/videos",
            {"upload_phase": "start", "file_size": str(file_size)},
            operation="video.start",
        )

    def transfer_video_chunk(
        self, upload_session_id: str, start_offset: int, chunk: bytes
    ) -> dict[str, Any]:
        """Send one chunk. The response dictates the next `start_offset`."""
        response = self._client.post(
            f"{self._settings.graph_base_url}/{self._page_id}/videos",
            data={
                "upload_phase": "transfer",
                "upload_session_id": upload_session_id,
                "start_offset": str(start_offset),
                "access_token": _page_token(),
            },
            files={"video_file_chunk": ("chunk", chunk, "application/octet-stream")},
        )
        return _unwrap(response, operation="video.transfer")

    def finish_video_session(
        self, upload_session_id: str, description: str, title: str = ""
    ) -> None:
        self._graph_post(
            f"{self._page_id}/videos",
            {
                "upload_phase": "finish",
                "upload_session_id": upload_session_id,
                "description": description,
                "title": title,
            },
            operation="video.finish",
        )

    def create_video_from_url(self, file_url: str, description: str, title: str = "") -> str:
        """Publish a feed video by URL, letting Meta download it."""
        data = self._graph_post(
            f"{self._page_id}/videos",
            {"file_url": file_url, "description": description, "title": title},
            operation="video.from_url",
        )
        return str(data["id"])

    # -- Status -----------------------------------------------------------

    def video_status(self, video_id: str) -> dict[str, Any]:
        """Read the upload/processing/publishing phases of a video."""
        data = self._graph_get(
            video_id, {"fields": "status,permalink_url"}, operation="video.status"
        )
        return data

"""Persistent credential storage with race-safe refresh.

Workers run concurrently, so refreshing a token is done under a row lock:
whichever worker wins re-reads the row and refreshes, the others block and
then observe the fresh value instead of burning a second refresh (TikTok
invalidates the previous refresh token on use).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from sau.config import get_settings
from sau.db import session_scope
from sau.errors import AuthError
from sau.logging import get_logger
from sau.models import OAuthToken

log = get_logger(__name__)

#: Refresh this far ahead of expiry so an in-flight upload never straddles it.
REFRESH_MARGIN_SECONDS = 600

#: `(access_token, refresh_token) -> (access_token, refresh_token, expires_in)`
RefreshFn = Callable[[str], tuple[str, str, int]]


def seed_token(
    platform: str,
    access_token: str,
    refresh_token: str | None = None,
    expires_in: int | None = None,
) -> None:
    """Insert or replace a platform's credentials.

    Called once after the initial OAuth handshake, and by `scripts/seed_tokens.py`
    to lift values out of the environment into the database.
    """
    if not access_token:
        raise AuthError("refusing to seed an empty access token", platform=platform)

    expires_at = (
        datetime.now(UTC) + timedelta(seconds=expires_in) if expires_in is not None else None
    )
    with session_scope() as session:
        row = session.get(OAuthToken, platform)
        if row is None:
            session.add(
                OAuthToken(
                    platform=platform,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=expires_at,
                )
            )
        else:
            row.access_token = access_token
            row.refresh_token = refresh_token or row.refresh_token
            row.expires_at = expires_at
    log.info("token.seeded", platform=platform, expires_at=expires_at)


def get_access_token(platform: str, refresh: RefreshFn | None = None) -> str:
    """Return a currently valid access token, refreshing it if needed.

    `refresh` is omitted for credentials that do not expire, such as a
    long-lived Facebook Page token.
    """
    with session_scope() as session:
        row = session.execute(
            select(OAuthToken).where(OAuthToken.platform == platform).with_for_update()
        ).scalar_one_or_none()

        if row is None:
            raise AuthError(
                f"no stored credentials for {platform}; run scripts/seed_tokens.py",
                platform=platform,
            )

        if refresh is None or not row.expires_within(REFRESH_MARGIN_SECONDS):
            return row.access_token

        if not row.refresh_token:
            raise AuthError("token expired and no refresh token stored", platform=platform)

        log.info("token.refreshing", platform=platform, expires_at=row.expires_at)
        access_token, refresh_token, expires_in = refresh(row.refresh_token)

        row.access_token = access_token
        row.refresh_token = refresh_token
        row.expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return access_token


def seed_from_settings() -> None:
    """Populate the token table from environment configuration."""
    settings = get_settings()
    if settings.facebook_page_access_token:
        seed_token("facebook", settings.facebook_page_access_token)
    if settings.tiktok_access_token:
        # Unknown remaining lifetime; assume it is due for refresh immediately.
        seed_token("tiktok", settings.tiktok_access_token, settings.tiktok_refresh_token, 0)

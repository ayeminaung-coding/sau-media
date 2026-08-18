"""Typed application settings, loaded once from the environment."""

import re
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Cloudflare account IDs are exactly 32 lowercase hex characters.
_R2_ACCOUNT_ID_RE = re.compile(r"[0-9a-f]{32}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    log_level: str = "INFO"

    #: Origins allowed to call the API from a browser. The console is a
    #: separate static origin, so it must be listed explicitly.
    cors_origins: list[str] = Field(default=["http://localhost:8080"])

    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "sau-media"
    r2_public_base_url: str = ""

    facebook_graph_version: str = "v21.0"
    facebook_app_id: str = ""
    facebook_app_secret: str = ""
    facebook_page_id: str = ""
    facebook_page_access_token: str = ""

    #: TikTok only accepts PULL_FROM_URL for domains verified in its developer
    #: portal. An r2.dev development URL cannot be verified, so this stays off
    #: until a custom domain is attached and verified. Facebook has no such
    #: requirement and uses `r2_public_base_url` regardless.
    tiktok_pull_from_url: bool = False

    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_access_token: str = ""
    tiktok_refresh_token: str = ""

    #: Upload chunk size for both platforms. Must satisfy TikTok's 5 MiB
    #: minimum / 64 MiB maximum window.
    chunk_size_bytes: int = Field(default=16 * 1024 * 1024, ge=5 * 1024 * 1024)

    @property
    def r2_endpoint_url(self) -> str:
        """Build the R2 endpoint, rejecting an account ID that cannot form one.

        Checked here rather than as a field validator so that a broken R2
        credential only fails the calls that actually need storage: the API
        still serves health, job listing and retries. Any string produces a
        syntactically valid host, so without this check a truncated ID is
        only caught when Cloudflare's edge refuses the TLS handshake for a
        subdomain it does not recognise -- surfacing as a bare
        `SSLV3_ALERT_HANDSHAKE_FAILURE` from botocore, several layers away
        from the setting that caused it.
        """
        if not _R2_ACCOUNT_ID_RE.fullmatch(self.r2_account_id):
            raise RuntimeError(
                f"R2_ACCOUNT_ID must be 32 lowercase hex characters, got "
                f"{len(self.r2_account_id)}. Copy it from the R2 overview sidebar, "
                "or from your dashboard URL (dash.cloudflare.com/<account-id>/r2)."
            )
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    @property
    def graph_base_url(self) -> str:
        return f"https://graph.facebook.com/{self.facebook_graph_version}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()  # type: ignore[call-arg]

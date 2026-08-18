"""Typed application settings, loaded once from the environment."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    log_level: str = "INFO"

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
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    @property
    def graph_base_url(self) -> str:
        return f"https://graph.facebook.com/{self.facebook_graph_version}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()  # type: ignore[call-arg]

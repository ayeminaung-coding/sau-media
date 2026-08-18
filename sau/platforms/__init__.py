"""Platform adapters.

Each platform implements `Publisher`. The queue talks only to that interface,
so adding YouTube later means adding one module and one registry entry.
"""

from sau.models import Platform
from sau.platforms.base import Publisher, PublishRequest, PublishResult, StatusResult
from sau.platforms.facebook.publisher import FacebookReelPublisher, FacebookVideoPublisher
from sau.platforms.tiktok.publisher import TikTokPublisher

_REGISTRY: dict[Platform, type[Publisher]] = {
    Platform.FACEBOOK_REEL: FacebookReelPublisher,
    Platform.FACEBOOK_VIDEO: FacebookVideoPublisher,
    Platform.TIKTOK: TikTokPublisher,
}


def get_publisher(platform: Platform) -> Publisher:
    """Instantiate the adapter registered for `platform`."""
    try:
        return _REGISTRY[platform]()
    except KeyError as exc:  # pragma: no cover - guarded by the Platform enum
        raise ValueError(f"no publisher registered for {platform}") from exc


__all__ = [
    "PublishRequest",
    "PublishResult",
    "Publisher",
    "StatusResult",
    "get_publisher",
]

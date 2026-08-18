"""Redis-backed job queues, one per platform.

Separate queues are the point of the design: a multi-gigabyte Facebook upload
occupying its worker for ten minutes must not delay a 40 MB TikTok post, and
either queue can be drained, paused, or scaled on its own.
"""

from functools import cache, lru_cache

from redis import Redis
from rq import Queue

from sau.config import get_settings
from sau.models import Platform

QUEUE_NAMES: dict[Platform, str] = {
    Platform.FACEBOOK_REEL: "facebook",
    Platform.FACEBOOK_VIDEO: "facebook",
    Platform.TIKTOK: "tiktok",
}

ALL_QUEUE_NAMES = sorted(set(QUEUE_NAMES.values()))


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


@cache
def get_queue(name: str) -> Queue:
    # Uploads are long; the default 180s job timeout would kill them mid-transfer.
    return Queue(name, connection=get_redis(), default_timeout=3600)


def queue_for(platform: Platform) -> Queue:
    return get_queue(QUEUE_NAMES[platform])

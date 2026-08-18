#!/usr/bin/env python3
"""Run an RQ worker against one or more platform queues.

Usage:
    python scripts/worker.py facebook
    python scripts/worker.py tiktok
    python scripts/worker.py            # every queue, for local development
"""

import sys

from rq import Worker

from sau.logging import configure_logging, get_logger
from sau.queue import ALL_QUEUE_NAMES, get_queue, get_redis

log = get_logger(__name__)


def main(names: list[str]) -> None:
    configure_logging()
    selected = names or ALL_QUEUE_NAMES

    unknown = set(selected) - set(ALL_QUEUE_NAMES)
    if unknown:
        raise SystemExit(f"unknown queue(s): {', '.join(sorted(unknown))}")

    log.info("worker.starting", queues=selected)
    Worker([get_queue(name) for name in selected], connection=get_redis()).work(
        with_scheduler=True
    )


if __name__ == "__main__":
    main(sys.argv[1:])

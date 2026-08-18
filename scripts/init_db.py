#!/usr/bin/env python3
"""Create tables and seed credentials from the environment.

Development convenience. Production should run Alembic migrations instead.
"""

from sau.db import create_all
from sau.logging import get_logger
from sau.tokens import seed_from_settings

log = get_logger(__name__)

if __name__ == "__main__":
    create_all()
    seed_from_settings()
    log.info("db.initialised")

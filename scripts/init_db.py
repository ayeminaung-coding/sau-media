#!/usr/bin/env python3
"""Create tables and seed credentials from the environment.

Development convenience. Production should run Alembic migrations instead.
"""

from sau.db import create_all, session_scope
from sau.logging import get_logger
from sau.schedule import ensure_default_slots
from sau.tokens import seed_from_settings

log = get_logger(__name__)

if __name__ == "__main__":
    create_all()
    seed_from_settings()
    # Only seeds an empty table, so re-running this never resets a schedule
    # the operator has since edited.
    with session_scope() as session:
        ensure_default_slots(session)
    log.info("db.initialised")

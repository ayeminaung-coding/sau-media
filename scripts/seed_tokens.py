#!/usr/bin/env python3
"""Copy platform credentials out of the environment into the token table.

Run once after the initial OAuth handshake, and again whenever a token is
re-issued by hand. TikTok tokens refresh themselves after that.
"""

from sau.logging import get_logger
from sau.tokens import seed_from_settings

log = get_logger(__name__)

if __name__ == "__main__":
    seed_from_settings()
    log.info("tokens.seeded")

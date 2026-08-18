#!/usr/bin/env python3
"""Apply the R2 bucket CORS policy the browser console needs.

Presigned PUT URLs are only half of the direct-to-R2 upload: the bucket must
also allow the console's origin, or the preflight fails and no bytes are ever
sent. Run this once per bucket, and again whenever CORS_ORIGINS changes.
"""

from sau import storage
from sau.config import get_settings
from sau.logging import get_logger

log = get_logger(__name__)

if __name__ == "__main__":
    settings = get_settings()
    storage.put_bucket_cors(settings.cors_origins)
    log.info("r2.cors.applied", bucket=settings.r2_bucket, origins=settings.cors_origins)

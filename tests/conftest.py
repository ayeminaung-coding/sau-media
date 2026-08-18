"""Test configuration.

Settings are read at import time, so the environment must be populated before
any `sau` module is imported.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("R2_PUBLIC_BASE_URL", "https://media.test")
os.environ.setdefault("FACEBOOK_PAGE_ID", "123456")

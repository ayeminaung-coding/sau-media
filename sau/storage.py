"""Object storage backed by Cloudflare R2 (S3-compatible).

R2 is chosen for its zero egress fees, which is what makes TikTok's
`PULL_FROM_URL` upload path free: TikTok downloads the video from us directly
instead of us streaming chunks to them.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config

from sau.config import get_settings

#: Boto's default is 4 retries with adaptive backoff; storage hiccups should
#: not surface as job failures.
_BOTO_CONFIG = Config(retries={"max_attempts": 5, "mode": "adaptive"}, signature_version="s3v4")


@lru_cache(maxsize=1)
def _client() -> Any:
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.r2_endpoint_url,
        aws_access_key_id=s.r2_access_key_id,
        aws_secret_access_key=s.r2_secret_access_key,
        region_name="auto",
        config=_BOTO_CONFIG,
    )


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int


def upload_file(local_path: Path, key: str, content_type: str = "video/mp4") -> StoredObject:
    """Upload a local file, using multipart automatically for large files."""
    bucket = get_settings().r2_bucket
    _client().upload_file(
        str(local_path), bucket, key, ExtraArgs={"ContentType": content_type}
    )
    return StoredObject(key=key, size_bytes=local_path.stat().st_size)


def download_file(key: str, local_path: Path) -> Path:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    _client().download_file(get_settings().r2_bucket, key, str(local_path))
    return local_path


def size_of(key: str) -> int:
    return int(_client().head_object(Bucket=get_settings().r2_bucket, Key=key)["ContentLength"])


def read_range(key: str, start: int, length: int) -> bytes:
    """Read `length` bytes starting at `start`. Used to feed chunked uploads."""
    end = start + length - 1
    response = _client().get_object(
        Bucket=get_settings().r2_bucket, Key=key, Range=f"bytes={start}-{end}"
    )
    return bytes(response["Body"].read())


def iter_chunks(key: str, chunk_size: int, start: int = 0) -> Iterator[tuple[int, bytes]]:
    """Yield `(offset, data)` pairs, resuming from `start`.

    Ranged reads rather than one streaming body, so a chunk that fails upload
    can be re-fetched without restarting the whole download.
    """
    total = size_of(key)
    offset = start
    while offset < total:
        length = min(chunk_size, total - offset)
        yield offset, read_range(key, offset, length)
        offset += length


def presigned_url(key: str, expires_seconds: int = 3600) -> str:
    """Time-limited URL for private objects."""
    return str(
        _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": get_settings().r2_bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
    )


def presigned_upload_url(
    key: str, expires_seconds: int = 3600, content_type: str = "video/mp4"
) -> str:
    """Time-limited PUT URL so clients upload straight to R2.

    Large source files must never be proxied through the API process.

    `content_type` is part of the SigV4 signature, so the caller must send the
    exact same value as the `Content-Type` header or R2 rejects the PUT with
    SignatureDoesNotMatch.
    """
    return str(
        _client().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": get_settings().r2_bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_seconds,
        )
    )


def put_bucket_cors(origins: list[str]) -> None:
    """Install the bucket CORS policy that browser-side PUTs depend on.

    A presigned URL authorises the upload but says nothing about which origin
    may issue it: without this policy the browser's preflight fails and the PUT
    never leaves the tab. `video/*` is not a CORS-simple Content-Type, so every
    console upload is preflighted.
    """
    _client().put_bucket_cors(
        Bucket=get_settings().r2_bucket,
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedOrigins": origins,
                    "AllowedMethods": ["PUT", "GET", "HEAD"],
                    "AllowedHeaders": ["content-type"],
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 3600,
                }
            ]
        },
    )


def public_url(key: str) -> str:
    """Stable URL on the bucket's custom domain.

    TikTok's `PULL_FROM_URL` only accepts URLs whose domain prefix has been
    verified in the developer portal, so presigned R2 endpoints will not work
    there. This must be a custom domain bound to the bucket.
    """
    base = get_settings().r2_public_base_url.rstrip("/")
    if not base:
        raise RuntimeError("R2_PUBLIC_BASE_URL is required for pull-based uploads")
    return f"{base}/{key.lstrip('/')}"


def delete(key: str) -> None:
    _client().delete_object(Bucket=get_settings().r2_bucket, Key=key)

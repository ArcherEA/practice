"""S3-compatible object storage (SeaweedFS locally, Cloudflare R2 on Vercel).

Only the plain S3 API through boto3 is used, so any compatible server works. Code
depends on the `Storage` protocol; tests inject a fake through the `get_storage`
FastAPI dependency.
"""

import logging
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Protocol
from urllib.parse import quote

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import Settings, settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

logger = logging.getLogger(__name__)

# The only types ever served inline; everything else is a forced download so a
# malicious file (SVG, HTML, ...) can never execute in the browser.
INLINE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})


class StorageNotConfiguredError(RuntimeError):
    """S3_* settings are missing."""


@dataclass(frozen=True)
class PresignedUpload:
    url: str
    headers: dict[str, str]


@dataclass(frozen=True)
class ObjectInfo:
    size: int


def is_inline_content_type(content_type: str) -> bool:
    return content_type.strip().lower() in INLINE_CONTENT_TYPES


def download_cache_control(*, expires_in: int, public: bool) -> str:
    """Cache-Control the bucket should send with a signed GET.

    Object keys are unique and objects never change, so a copy is valid for as long as
    the signed URL is: `immutable` also stops reload-time revalidation. `public` is only
    for files meant for everyone (public images); everything else stays `private`.
    """
    scope = "public" if public else "private"
    return f"{scope}, max-age={max(expires_in, 0)}, immutable"


def content_disposition(filename: str, *, inline: bool) -> str:
    if inline:
        return "inline"
    return f"attachment; filename*=UTF-8''{quote(filename, safe='')}"


class Storage(Protocol):
    def presign_upload(
        self, key: str, *, content_type: str, size: int, expires_in: int
    ) -> PresignedUpload: ...

    def presign_download(
        self,
        key: str,
        *,
        filename: str,
        content_type: str,
        expires_in: int,
        public: bool = False,
    ) -> str: ...

    def public_url(self, key: str) -> str | None: ...

    def head(self, key: str) -> ObjectInfo | None: ...

    def delete(self, key: str) -> None: ...


class S3Storage:
    """boto3-backed `Storage`. Clients are created lazily (no network on creation)."""

    def __init__(self, config: Settings) -> None:
        self._config = config

    def _make_client(self, endpoint_url: str) -> S3Client:
        cfg = self._config
        if not (cfg.S3_BUCKET and cfg.S3_ACCESS_KEY_ID and cfg.S3_SECRET_ACCESS_KEY):
            raise StorageNotConfiguredError("File storage is not configured")
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=cfg.S3_REGION,
            aws_access_key_id=cfg.S3_ACCESS_KEY_ID,
            aws_secret_access_key=cfg.S3_SECRET_ACCESS_KEY,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                # Newer boto3 adds CRC checksums by default, which R2 and others reject.
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                connect_timeout=5,
                read_timeout=10,
                retries={"max_attempts": 2},
            ),
        )

    @cached_property
    def _client(self) -> S3Client:
        """Talks to the bucket from the backend (internal hostname)."""
        if not self._config.S3_ENDPOINT_URL:
            raise StorageNotConfiguredError("File storage is not configured")
        return self._make_client(self._config.S3_ENDPOINT_URL)

    @cached_property
    def _signer(self) -> S3Client:
        """Only used to presign: the URL embeds the hostname the browser will use."""
        # S3_ENDPOINT_URL is what makes storage "configured"; the public endpoint only
        # overrides the hostname in signed URLs. Without it we'd hand out links the
        # backend itself can never verify (confirm/HEAD would fail).
        if not self._config.S3_ENDPOINT_URL:
            raise StorageNotConfiguredError("File storage is not configured")
        endpoint = self._config.S3_PUBLIC_ENDPOINT_URL or self._config.S3_ENDPOINT_URL
        return self._make_client(endpoint)

    @property
    def _bucket(self) -> str:
        if not self._config.S3_BUCKET:
            raise StorageNotConfiguredError("File storage is not configured")
        return self._config.S3_BUCKET

    def presign_upload(
        self, key: str, *, content_type: str, size: int, expires_in: int
    ) -> PresignedUpload:
        # R2 has no presigned POST, so PUT it is. ContentLength and ContentType are
        # part of the signature: the bucket rejects a body of another size or type.
        # StorageClass is deliberately never set (R2 free tier = Standard only).
        url = self._signer.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
                "ContentLength": size,
            },
            ExpiresIn=expires_in,
        )
        return PresignedUpload(url=url, headers={"Content-Type": content_type})

    def presign_download(
        self,
        key: str,
        *,
        filename: str,
        content_type: str,
        expires_in: int,
        public: bool = False,
    ) -> str:
        # ResponseCacheControl is a signed *query* parameter (response-cache-control):
        # no request header, so bucket CORS (and the upload flow) are unaffected.
        return self._signer.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ResponseContentDisposition": content_disposition(
                    filename, inline=is_inline_content_type(content_type)
                ),
                "ResponseCacheControl": download_cache_control(
                    expires_in=expires_in, public=public
                ),
            },
            ExpiresIn=expires_in,
        )

    def public_url(self, key: str) -> str | None:
        base = self._config.S3_PUBLIC_BASE_URL
        if not base:
            return None
        return f"{base.rstrip('/')}/{quote(key, safe='/')}"

    def head(self, key: str) -> ObjectInfo | None:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                return None
            raise
        return ObjectInfo(size=response["ContentLength"])

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)


_storage = S3Storage(settings)


def get_storage() -> Storage:
    """FastAPI dependency; override in tests with a fake."""
    return _storage


def delete_objects_quietly(storage: Storage, keys: list[str]) -> None:
    """Best-effort object removal: failures are logged, never raised."""
    for key in keys:
        try:
            storage.delete(key)
        except Exception:
            logger.warning("Could not delete storage object %s", key, exc_info=True)

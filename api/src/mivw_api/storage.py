"""Object storage.

Bulk data never traverses the gateway: clients upload and download directly via
short-lived presigned URLs. See ADR 0003.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import structlog

if TYPE_CHECKING:
    from mivw_api.config import Settings

log = structlog.get_logger(__name__)


class ObjectStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._endpoint = settings.object_endpoint.rstrip("/")
        self._bucket = settings.object_bucket
        self._ttl = settings.presigned_url_ttl_seconds

    @property
    def bucket(self) -> str:
        return self._bucket

    def expiry(self) -> datetime:
        return datetime.now(UTC) + timedelta(seconds=self._ttl)

    @staticmethod
    def content_key(prefix: str, digest: bytes, suffix: str = "") -> str:
        """Content-addressed key.

        Derived from the payload hash, never from a client-supplied filename,
        which removes path traversal as a concern entirely.
        """
        hex_digest = digest.hex()
        return f"{prefix}/{hex_digest[:2]}/{hex_digest}{suffix}"

    @staticmethod
    def digest(payload: bytes) -> bytes:
        return hashlib.sha256(payload).digest()

    async def presign_get(self, key: str) -> str:
        async with self._client() as client:
            return cast(
                str,
                await client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": key},
                    ExpiresIn=self._ttl,
                ),
            )

    async def presign_put(self, key: str, *, max_bytes: int) -> str:
        mode = getattr(self._settings.mode, "value", self._settings.mode)
        params: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "ContentLength": max_bytes,
        }
        if mode != "local":
            params["ServerSideEncryption"] = "aws:kms"
        async with self._client() as client:
            return cast(
                str,
                await client.generate_presigned_url(
                    "put_object",
                    Params=params,
                    ExpiresIn=self._ttl,
                ),
            )

    async def get_object(self, key: str, *, expected_sha256: bytes | None = None) -> bytes:
        async with self._client() as client:
            response = await client.get_object(Bucket=self._bucket, Key=key)
            payload: bytes = await response["Body"].read()

        # Verify on read: the database holds the authoritative hash, so silent
        # corruption or substitution in the object store is caught here.
        if expected_sha256 is not None:
            actual = hashlib.sha256(payload).digest()
            if actual != expected_sha256:
                log.error("storage.integrity_failure", key=key)
                raise IntegrityError(f"content hash mismatch for object {key}")

        return payload

    async def put_object(self, key: str, payload: bytes) -> bytes:
        digest = hashlib.sha256(payload).digest()
        mode = getattr(self._settings.mode, "value", self._settings.mode)
        put_kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": payload,
        }
        if mode != "local":
            put_kwargs["ServerSideEncryption"] = "aws:kms"
        async with self._client() as client:
            await client.put_object(**put_kwargs)
        return digest

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[Any]:
        import aioboto3  # type: ignore[import-untyped]

        session = aioboto3.Session()
        client_kwargs = {
            "endpoint_url": self._endpoint,
            "region_name": self._settings.object_region,
        }
        mode = getattr(self._settings.mode, "value", self._settings.mode)
        if mode == "local":
            client_kwargs.update(
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "mivwdev"),
                aws_secret_access_key=os.environ.get(
                    "AWS_SECRET_ACCESS_KEY", "devonly_not_for_deployment"
                ),
            )
        async with session.client("s3", **client_kwargs) as client:
            yield client


class IntegrityError(RuntimeError):
    """Stored object does not match its recorded hash."""

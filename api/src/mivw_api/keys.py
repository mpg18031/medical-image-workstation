"""Key resolution.

Key *material* never comes from configuration or the database - only key
identifiers do. In `local` mode keys come from the OS keychain; in `server`
mode from a KMS. Storing an encryption key next to the ciphertext it protects
would make the encryption decorative.
"""

from __future__ import annotations

import functools
import os

import structlog

from mivw_api.config import Mode, Settings

log = structlog.get_logger(__name__)


class KeyUnavailableError(RuntimeError):
    """The configured key could not be resolved from its backing store."""


@functools.lru_cache(maxsize=8)
def _resolve(key_id: str, mode: Mode) -> bytes:
    # Tests and local development may inject material directly. This is
    # deliberately not read in server mode.
    override = os.environ.get(f"MIVW_KEY_MATERIAL_{key_id.upper().replace('-', '_')}")
    if override and mode is Mode.LOCAL:
        return override.encode()

    if mode is Mode.LOCAL:
        try:
            import keyring

            secret = keyring.get_password("mivw", key_id)
        except ImportError as exc:
            raise KeyUnavailableError(
                "python-keyring is required to resolve keys in local mode"
            ) from exc

        if secret is None:
            raise KeyUnavailableError(
                f"key '{key_id}' is not present in the OS keychain. "
                f"Add it with: keyring set mivw {key_id}"
            )
        return secret.encode()

    return _resolve_from_kms(key_id)


def _resolve_from_kms(key_id: str) -> bytes:
    try:
        import boto3  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - server-mode dependency
        raise KeyUnavailableError("boto3 is required to resolve keys in server mode") from exc

    client = boto3.client("kms")
    response = client.generate_data_key(KeyId=key_id, KeySpec="AES_256")
    plaintext: bytes = response["Plaintext"]
    return plaintext


def get_hmac_key(settings: Settings) -> bytes:
    """Key for the searchable identifier HMAC."""
    return _resolve(settings.hmac_key_id, settings.mode)


def get_encryption_key(settings: Settings) -> bytes:
    """Key for column-level PHI encryption."""
    return _resolve(settings.encryption_key_id, settings.mode)


def clear_cache() -> None:
    """Drop cached material, for rotation and for test isolation."""
    _resolve.cache_clear()

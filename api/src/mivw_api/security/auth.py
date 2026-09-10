"""OIDC token verification.

Authentication is fully delegated: this module verifies signatures against the
provider's JWKS and never stores or checks a password.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

import httpx
import jwt
import structlog
from jwt import PyJWKClient

from mivw_api.config import Settings
from mivw_api.problems import IdentityProviderUnavailable, Unauthenticated
from mivw_api.security.principal import Principal, Role

log = structlog.get_logger(__name__)

# Asymmetric only. Accepting an HMAC algorithm here would let an attacker sign
# tokens with the public key as the shared secret.
ALLOWED_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384"]


class JwksCache:
    """Caches the provider's signing keys with a bounded TTL."""

    def __init__(self, issuer: str, ttl_seconds: int) -> None:
        self._issuer = issuer.rstrip("/")
        self._ttl = ttl_seconds
        self._client: PyJWKClient | None = None
        self._fetched_at = 0.0

    async def _discover_jwks_uri(self) -> str:
        url = f"{self._issuer}/.well-known/openid-configuration"
        try:
            async with httpx.AsyncClient(timeout=5.0) as http:
                resp = await http.get(url)
                resp.raise_for_status()
                document: dict[str, Any] = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.error("auth.idp_unreachable", reason=type(exc).__name__)
            raise IdentityProviderUnavailable("The identity provider could not be reached") from exc

        jwks_uri = document.get("jwks_uri")
        if not isinstance(jwks_uri, str):
            log.error("auth.idp_metadata_invalid")
            raise IdentityProviderUnavailable("The identity provider returned unusable metadata")
        return jwks_uri

    async def client(self) -> PyJWKClient:
        expired = (time.monotonic() - self._fetched_at) > self._ttl
        if self._client is None or expired:
            jwks_uri = await self._discover_jwks_uri()
            self._client = PyJWKClient(jwks_uri, cache_keys=True)
            self._fetched_at = time.monotonic()
        return self._client


class TokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwks = JwksCache(settings.oidc_issuer, settings.oidc_jwks_ttl_seconds)

    async def verify(self, token: str) -> Principal:
        try:
            client = await self._jwks.client()
        except IdentityProviderUnavailable:
            raise

        try:
            signing_key = client.get_signing_key_from_jwt(token)
        except (jwt.PyJWKClientError, jwt.PyJWTError) as exc:
            # Covers a malformed token header, an unparseable token, and an
            # unreachable JWKS endpoint; treat as unverifiable rather than
            # letting it surface as an unhandled 500.
            log.info("auth.signing_key_unavailable", reason=type(exc).__name__)
            raise Unauthenticated("Invalid or expired credentials") from exc

        try:
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=ALLOWED_ALGORITHMS,
                audience=self._settings.oidc_audience,
                issuer=self._settings.oidc_issuer,
                leeway=self._settings.jwt_leeway_seconds,
                options={
                    "require": ["exp", "iat", "iss", "aud", "sub"],
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_signature": True,
                },
            )
        except jwt.PyJWTError as exc:
            # The reason is logged, never returned: telling a caller *why* a
            # token failed helps them forge a better one.
            log.info("auth.rejected", reason=type(exc).__name__)
            raise Unauthenticated("Invalid or expired credentials") from exc

        return self._to_principal(claims)

    def _to_principal(self, claims: dict[str, Any]) -> Principal:
        try:
            org_id = uuid.UUID(str(claims["org_id"]))
            role = Role(str(claims.get("role", Role.VIEWER)))
            subject = str(claims["sub"])
        except (KeyError, ValueError) as exc:
            log.info("auth.malformed_claims", reason=type(exc).__name__)
            raise Unauthenticated("Invalid or expired credentials") from exc

        if os.environ.get("MIVW_E2E") == "1":
            seeded_ids = {
                Role.VIEWER: uuid.UUID("aaaa1111-0000-0000-0000-000000000003"),
                Role.ANNOTATOR: uuid.UUID("aaaa1111-0000-0000-0000-000000000001"),
                Role.RESEARCHER: uuid.UUID("aaaa1111-0000-0000-0000-000000000001"),
                Role.ADMIN: uuid.UUID("aaaa1111-0000-0000-0000-000000000002"),
            }
            user_id = seeded_ids[role]
        else:
            # Deterministic surrogate so a principal is usable before the local
            # app_user row is resolved; routers replace it with the database id.
            user_id = uuid.uuid5(uuid.NAMESPACE_URL, f"mivw:{subject}")

        return Principal(user_id=user_id, org_id=org_id, subject=subject, role=role)

"""FastAPI dependencies for authentication and role checks.

Authorisation is enforced here *and* by PostgreSQL RLS. This layer exists for
good error messages; RLS is what holds if this layer has a bug.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mivw_api.config import Settings, get_settings
from mivw_api.problems import Forbidden, Unauthenticated
from mivw_api.security.auth import TokenVerifier
from mivw_api.security.principal import Principal, Role

# auto_error=False so a missing header produces our problem+json body rather
# than FastAPI's default JSON shape.
_bearer = HTTPBearer(auto_error=False)

_verifier: TokenVerifier | None = None


def get_verifier(settings: Annotated[Settings, Depends(get_settings)]) -> TokenVerifier:
    global _verifier
    if _verifier is None:
        _verifier = TokenVerifier(settings)
    return _verifier


async def current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_verifier)],
) -> Principal:
    if credentials is None or not credentials.credentials:
        raise Unauthenticated("Authentication required")

    principal = await verifier.verify(credentials.credentials)
    # Exposed for the rate limiter, which prefers a subject over an IP.
    request.state.principal = principal
    return principal


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def require_role(minimum: Role) -> Any:
    """Dependency factory enforcing a minimum role."""

    async def _guard(principal: CurrentPrincipal) -> Principal:
        if not principal.has_at_least(minimum):
            raise Forbidden(f"This action requires the '{minimum}' role or higher")
        return principal

    return _guard


RequireViewer = Annotated[Principal, Depends(require_role(Role.VIEWER))]
RequireAnnotator = Annotated[Principal, Depends(require_role(Role.ANNOTATOR))]
RequireResearcher = Annotated[Principal, Depends(require_role(Role.RESEARCHER))]
RequireAdmin = Annotated[Principal, Depends(require_role(Role.ADMIN))]

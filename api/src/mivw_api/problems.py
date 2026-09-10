"""RFC 9457 problem details.

Problem bodies are returned to clients, so they must never contain PHI or
internal diagnostics. Messages reference field names and constraint codes only.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_BASE = "https://mivw.local/problems"


class FieldError(BaseModel):
    field: str
    code: str


class ProblemDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = Field(default=None, alias="requestId")
    errors: list[FieldError] | None = None


class ProblemError(Exception):
    """Base for errors that cross the API boundary."""

    problem_type: str = f"{_BASE}/error"
    title: str = "Error"
    status: int = 500

    def __init__(
        self,
        detail: str | None = None,
        *,
        errors: list[FieldError] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.errors = errors

    def to_problem(self, *, instance: str | None = None) -> ProblemDetail:
        return ProblemDetail(
            type=self.problem_type,
            title=self.title,
            status=self.status,
            detail=self.detail,
            instance=instance,
            errors=self.errors,
        )


class Unauthenticated(ProblemError):
    problem_type = f"{_BASE}/unauthenticated"
    title = "Authentication required"
    status = 401


class Forbidden(ProblemError):
    problem_type = f"{_BASE}/forbidden"
    title = "Insufficient permissions"
    status = 403


class NotFound(ProblemError):
    """Also returned when RLS filters a row out.

    Distinguishing "forbidden" from "absent" would leak the existence of another
    tenant's study, so both cases produce 404.
    """

    problem_type = f"{_BASE}/not-found"
    title = "Resource not found"
    status = 404


class Conflict(ProblemError):
    problem_type = f"{_BASE}/conflict"
    title = "Conflicting state"
    status = 409


class ValidationFailed(ProblemError):
    problem_type = f"{_BASE}/validation-failed"
    title = "Request validation failed"
    status = 422


class SpecMismatch(ProblemError):
    problem_type = f"{_BASE}/volume-spec-mismatch"
    title = "Volume does not satisfy model input specification"
    status = 422


class DigestMismatch(ProblemError):
    problem_type = f"{_BASE}/artifact-digest-mismatch"
    title = "Artifact digest does not match the registry entry"
    status = 409


class QuarantinedSeries(ProblemError):
    problem_type = f"{_BASE}/series-quarantined"
    title = "Series is quarantined pending burned-in annotation review"
    status = 409


class RateLimited(ProblemError):
    problem_type = f"{_BASE}/rate-limited"
    title = "Too many requests"
    status = 429


class GpuUnavailable(ProblemError):
    problem_type = f"{_BASE}/gpu-unavailable"
    title = "No GPU capacity available"
    status = 503


class IdentityProviderUnavailable(ProblemError):
    """The OIDC provider could not be reached to verify a token.

    Distinct from 401: the credentials may be perfectly valid, so telling the
    client to re-authenticate would send them into a loop.
    """

    problem_type = f"{_BASE}/identity-provider-unavailable"
    title = "Unable to verify credentials at this time"
    status = 503

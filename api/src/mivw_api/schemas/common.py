"""Shared schema primitives."""

from __future__ import annotations

import base64
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")


def to_camel(snake: str) -> str:
    head, *tail = snake.split("_")
    return head + "".join(word.capitalize() for word in tail)


class Schema(BaseModel):
    """Base for every request and response model.

    `extra="forbid"` matters on requests: silently ignoring an unknown field
    means a client typo becomes a silent no-op instead of a 422.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class Page(Schema, Generic[T]):
    items: list[T]
    next_cursor: str | None = Field(
        default=None,
        description="Opaque keyset cursor. Absent when there are no further pages.",
    )


class Vec3(Schema):
    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


Sha256Hex = Annotated[
    str,
    Field(
        pattern=r"^[0-9a-f]{64}$",
        description="Lowercase hex SHA-256 digest",
        examples=["9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"],
    ),
]

ObjectKey = Annotated[
    str,
    Field(
        min_length=1,
        max_length=512,
        # Object keys are derived from content hashes, never from user input;
        # this pattern blocks traversal attempts at the boundary anyway.
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$",
    ),
]


class Sha256Field(Schema):
    value: Sha256Hex

    @field_validator("value")
    @classmethod
    def _lowercase(cls, v: str) -> str:
        return v.lower()

    def as_bytes(self) -> bytes:
        return bytes.fromhex(self.value)


def encode_cursor(*parts: object) -> str:
    raw = "\x1f".join(str(p) for p in parts).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> list[str]:
    padding = "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(cursor + padding)
    return raw.decode().split("\x1f")

"""The authenticated caller."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    VIEWER = "viewer"
    ANNOTATOR = "annotator"
    RESEARCHER = "researcher"
    ADMIN = "admin"


# Higher rank implies every capability of the ranks below it.
_RANK: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.ANNOTATOR: 1,
    Role.RESEARCHER: 2,
    Role.ADMIN: 3,
}


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: uuid.UUID
    org_id: uuid.UUID
    subject: str
    role: Role

    def has_at_least(self, required: Role) -> bool:
        return _RANK[self.role] >= _RANK[required]

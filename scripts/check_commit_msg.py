#!/usr/bin/env python3
"""Enforce Conventional Commits so the changelog can be generated from history."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERN = re.compile(
    r"^(?P<type>build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)"
    r"(?P<scope>\([a-z0-9\-/]+\))?(?P<breaking>!)?: (?P<subject>.{1,72})$"
)

EXAMPLES = """
  feat(render): add oblique reformat to the MPR pane
  fix(api): return 404 instead of 403 for cross-tenant studies
  docs(adr): record the off-screen rendering decision
  feat(db)!: drop the legacy annotation payload column
"""


def main() -> int:
    message_file = Path(sys.argv[1])
    lines = message_file.read_text(encoding="utf-8").splitlines()

    subject = next((line for line in lines if line and not line.startswith("#")), "")

    if subject.startswith(("Merge ", "Revert ", "fixup!", "squash!")):
        return 0

    if not PATTERN.match(subject):
        print(f"Invalid commit subject:\n  {subject}\n")
        print(f"Expected <type>(<scope>): <subject>, for example:{EXAMPLES}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

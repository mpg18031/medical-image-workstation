"""Shared fixtures for the pgTAP suite.

`make test-db` runs `pytest db/tests` standalone, so this package needs its
own `migrated_dsn` fixture (it cannot see api/tests/conftest.py). Honours
MIVW_DB_DSN if set (e.g. a developer's local PostgreSQL); otherwise falls
back to an ephemeral container, same as the API suite.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _apply_migrations(dsn: str) -> None:
    subprocess.run(  # noqa: S603
        [sys.executable, str(REPO_ROOT / "scripts" / "migrate.py"), "apply"],  # noqa: S607
        check=True,
        env={"MIVW_DB_DSN": dsn, "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )


@pytest.fixture(scope="session")
def migrated_dsn() -> Iterator[str]:
    dsn = os.environ.get("MIVW_DB_DSN")
    if dsn:
        _apply_migrations(dsn)
        yield dsn
        return

    from testcontainers.postgres import PostgresContainer

    image = os.environ.get("MIVW_TEST_POSTGRES_IMAGE", "postgres:16-alpine")
    with PostgresContainer(image, driver=None) as container:
        container_dsn = container.get_connection_url()
        _apply_migrations(container_dsn)
        yield container_dsn

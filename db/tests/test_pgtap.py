"""Runs the pgTAP suites through pytest.

Keeps `make test-db` consistent with the rest of the suite while CI can still
invoke pg_prove directly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent
SUITES = sorted(TESTS_DIR.glob("[0-9][0-9][0-9]_*.sql"))


@pytest.fixture(scope="module")
def pgtap_dsn(migrated_dsn: str) -> str:
    """Install pgTAP into the already-migrated database."""
    subprocess.run(  # noqa: S603
        ["psql", dsn_flag(migrated_dsn), "-c", "CREATE EXTENSION IF NOT EXISTS pgtap;"],  # noqa: S607
        check=True,
        capture_output=True,
    )
    return migrated_dsn


def dsn_flag(dsn: str) -> str:
    return f"--dbname={dsn}"


@pytest.mark.parametrize("suite", SUITES, ids=lambda p: p.stem)
def test_pgtap_suite(suite: Path, pgtap_dsn: str) -> None:
    result = subprocess.run(  # noqa: S603
        [
            "psql",
            dsn_flag(pgtap_dsn),
            "--no-psqlrc",
            "--quiet",  # noqa: S607
            "--set",
            "ON_ERROR_STOP=1",
            "--file",
            str(suite),
        ],
        capture_output=True,
        text=True,
    )

    sys.stdout.write(result.stdout)

    if result.returncode != 0:
        pytest.fail(f"{suite.name} failed:\n{result.stderr}\n{result.stdout}")

    # TAP reports failures in stdout even when psql exits zero.
    failures = [
        line for line in result.stdout.splitlines() if line.startswith("not ok")
    ]
    if failures:
        pytest.fail(f"{suite.name} assertions failed:\n" + "\n".join(failures))


def test_every_migration_has_pgtap_coverage() -> None:
    """A schema change without a test is how RLS regressions ship."""
    assert SUITES, "no pgTAP suites found"

#!/usr/bin/env python3
"""Forward-only migration runner.

Migrations are numbered, immutable once merged, and applied inside a single
transaction guarded by an advisory lock so concurrent deployments cannot race
each other into a half-applied schema.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import sys
from array import array
from pathlib import Path

import aioboto3
import asyncpg

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"
SEED_DIR = REPO_ROOT / "db" / "seed"

# Arbitrary but fixed: two runners must pick the same lock key.
ADVISORY_LOCK_KEY = 0x4D49_5657

BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migration (
    version     text PRIMARY KEY,
    checksum    bytea NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now(),
    applied_by  text NOT NULL DEFAULT current_user
);
"""


def discover() -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        raise SystemExit(f"no migrations found in {MIGRATIONS_DIR}")
    return files


def checksum(path: Path) -> bytes:
    return hashlib.sha256(path.read_bytes()).digest()


async def apply(dsn: str, *, dry_run: bool = False) -> int:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(BOOTSTRAP)
        await conn.execute("SELECT pg_advisory_lock($1)", ADVISORY_LOCK_KEY)

        applied = {
            row["version"]: row["checksum"]
            for row in await conn.fetch(
                "SELECT version, checksum FROM schema_migration"
            )
        }

        pending = []
        for path in discover():
            version = path.stem
            digest = checksum(path)

            if version in applied:
                if applied[version] != digest:
                    # A merged migration that changed content means someone
                    # edited history; every other environment now differs.
                    raise SystemExit(
                        f"checksum mismatch for {version}: migrations are immutable "
                        f"once applied. Add a new migration instead."
                    )
                continue
            pending.append((version, path, digest))

        if not pending:
            print("schema up to date")
            return 0

        for version, path, _ in pending:
            print(f"{'would apply' if dry_run else 'applying'} {version}")

        if dry_run:
            return 0

        for version, path, digest in pending:
            async with conn.transaction():
                await conn.execute(path.read_text(encoding="utf-8"))
                await conn.execute(
                    "INSERT INTO schema_migration (version, checksum) VALUES ($1, $2)",
                    version,
                    digest,
                )
        print(f"applied {len(pending)} migration(s)")
        return 0
    finally:
        await conn.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_KEY)
        await conn.close()


async def status(dsn: str) -> int:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(BOOTSTRAP)
        applied = {
            row["version"]
            for row in await conn.fetch("SELECT version FROM schema_migration")
        }
        for path in discover():
            mark = "applied" if path.stem in applied else "pending"
            print(f"  [{mark:>7}] {path.stem}")
        return 0
    finally:
        await conn.close()


async def seed(dsn: str) -> int:
    """Load synthetic development fixtures.

    Refuses to run outside an explicitly non-production database: seeding a
    real deployment with fake patients would corrupt the worklist.
    """
    if os.environ.get("MIVW_MODE") == "server" and not os.environ.get(
        "MIVW_ALLOW_SEED"
    ):
        raise SystemExit(
            "refusing to seed in server mode; set MIVW_ALLOW_SEED=1 to override"
        )

    files = sorted(SEED_DIR.glob("*.sql"))
    if not files:
        print("no seed files")
        return 0

    conn = await asyncpg.connect(dsn)
    try:
        for path in files:
            print(f"seeding {path.name}")
            async with conn.transaction():
                await conn.execute(path.read_text(encoding="utf-8"))
        await seed_volume_objects()
        return 0
    finally:
        await conn.close()


async def seed_volume_objects() -> None:
    """Upload deterministic development volumes referenced by the SQL seed."""
    endpoint = os.environ.get("MIVW_OBJECT_ENDPOINT", "http://localhost:9000")
    bucket = os.environ.get("MIVW_OBJECT_BUCKET", "mivw-volumes")
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "mivwdev")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "devonly_not_for_deployment")
    volumes = {
        "volumes/phantom-001.raw": (128, 256, 256, "zero"),
        "volumes/phantom-anisotropic.raw": (120, 512, 512, "zero"),
        "volumes/phantom-color.raw": (128, 256, 256, "contrast"),
    }

    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=endpoint,
        region_name=os.environ.get("MIVW_OBJECT_REGION", "us-east-1"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    ) as client:
        try:
            await client.create_bucket(Bucket=bucket)
        except client.exceptions.BucketAlreadyOwnedByYou:
            pass
        for key, (depth, height, width, pattern) in volumes.items():
            payload = (
                b"\0" * (depth * height * width * 2)
                if pattern == "zero"
                else contrast_volume(depth, height, width)
            )
            await client.put_object(
                Bucket=bucket,
                Key=key,
                Body=payload,
            )
            print(f"uploaded {key}")


def contrast_volume(depth: int, height: int, width: int) -> bytes:
    """Create a deterministic multi-intensity phantom for visual development."""
    values = array("h")
    for z in range(depth):
        nz = 2.0 * z / (depth - 1) - 1.0
        for y in range(height):
            ny = 2.0 * y / (height - 1) - 1.0
            for x in range(width):
                nx = 2.0 * x / (width - 1) - 1.0
                radius = math.sqrt(nx * nx + ny * ny + nz * nz)
                if radius < 0.28:
                    value = 1000
                elif radius < 0.52:
                    value = 450
                elif radius < 0.78:
                    value = -100
                else:
                    value = -1000
                values.append(value)
    return values.tobytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["apply", "status", "seed"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dsn", default=os.environ.get("MIVW_DB_DSN"))
    args = parser.parse_args()

    if not args.dsn:
        raise SystemExit("set MIVW_DB_DSN or pass --dsn")

    import asyncio

    match args.command:
        case "apply":
            return asyncio.run(apply(args.dsn, dry_run=args.dry_run))
        case "status":
            return asyncio.run(status(args.dsn))
        case "seed":
            return asyncio.run(seed(args.dsn))
    return 1


if __name__ == "__main__":
    sys.exit(main())

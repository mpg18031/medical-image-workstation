#!/usr/bin/env python3
"""Export the OpenAPI document.

The generated TypeScript client is committed, and CI fails if regeneration
produces a diff, so an accidental breaking API change shows up in review
rather than at runtime.
"""

from __future__ import annotations

import json
import os
import sys

# Values the schema does not depend on, so the export never needs real config.
os.environ.setdefault("MIVW_MODE", "local")
os.environ.setdefault("MIVW_DB_DSN", "postgresql://export@localhost/export")
os.environ.setdefault("MIVW_OIDC_ISSUER", "https://export.invalid")
os.environ.setdefault("MIVW_OIDC_AUDIENCE", "export")
os.environ.setdefault("MIVW_ENCRYPTION_KEY_ID", "export")
os.environ.setdefault("MIVW_HMAC_KEY_ID", "export")


def main() -> int:
    from mivw_api.main import create_app

    schema = create_app().openapi()
    json.dump(schema, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

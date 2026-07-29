#!/usr/bin/env python3
"""Verify connectivity, extensions, and Alembic revision."""

from __future__ import annotations

import sys

from openleadkit.config import get_settings
from openleadkit.database import build_engine, inspect_database


def main() -> int:
    settings = get_settings()
    print(f"Connection: {settings.masked_database_url}")
    try:
        health = inspect_database(build_engine(settings.database_url))
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"PostgreSQL: {health.version}")
    print(f"Database: {health.database}")
    print(f"User: {health.user}")
    print(f"Extensions: {', '.join(sorted(health.extensions)) or 'none'}")
    print(f"Alembic revision: {health.migration_revision or 'not migrated'}")
    if health.missing_extensions:
        print(
            f"FAILED: missing extensions: {', '.join(health.missing_extensions)}",
            file=sys.stderr,
        )
        return 1
    if not health.migrations_current:
        print("FAILED: run `alembic upgrade head`", file=sys.stderr)
        return 1
    print("OK: database is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

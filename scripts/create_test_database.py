#!/usr/bin/env python3
"""Create a safe test database without dropping anything."""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from openleadkit.config import get_settings
from openleadkit.database import validate_test_database_urls


def main() -> int:
    settings = get_settings()
    try:
        test_url = validate_test_database_urls(settings)
    except Exception as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 2
    url = make_url(test_url)
    database = url.database or ""
    admin_url = url.set(database="postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            exists = connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": database}
            )
            if exists:
                print(f"Database `{database}` already exists; no changes were made.")
                return 0
            quoted = connection.dialect.identifier_preparer.quote(database)
            connection.execute(text(f"CREATE DATABASE {quoted}"))
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"Database `{database}` was created.")
    print("Next step: DATABASE_URL=$TEST_DATABASE_URL alembic upgrade head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

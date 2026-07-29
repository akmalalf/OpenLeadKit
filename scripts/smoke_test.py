#!/usr/bin/env python3
"""Offline-by-default smoke test for configuration and local dependencies."""

from __future__ import annotations

import sys

from openleadkit.config import get_settings
from openleadkit.database import build_engine, inspect_database
from openleadkit.services.categories import load_categories
from openleadkit.services.excel_exporter import inspect_workbook


def main() -> int:
    failures: list[str] = []
    try:
        settings = get_settings()
        print("OK configuration")
    except Exception as exc:
        print(f"FAILED configuration: {exc}")
        return 1
    try:
        categories = load_categories()
        print(f"OK categories: {len(categories)}")
    except Exception as exc:
        failures.append(f"categories: {exc}")
    try:
        health = inspect_database(build_engine(settings.database_url))
        if health.missing_extensions or not health.migrations_current:
            failures.append("database extensions or migrations are not current")
        else:
            print(f"OK database: {health.database}, revision {health.migration_revision}")
    except Exception as exc:
        failures.append(f"database: {exc}")
    if settings.excel_input.exists():
        try:
            workbook = inspect_workbook(settings.excel_input)
            print(f"OK workbook: header {workbook.header_row}")
        except Exception as exc:
            failures.append(f"workbook: {exc}")
    else:
        print(f"INFO optional workbook is not present: {settings.excel_input}")
    if failures:
        for failure in failures:
            print(f"FAILED {failure}", file=sys.stderr)
        return 1
    print("OK smoke test; no external network requests were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

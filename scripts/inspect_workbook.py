#!/usr/bin/env python3
"""Inspect the configured workbook without saving changes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from openleadkit.config import get_settings
from openleadkit.services.excel_exporter import inspect_workbook


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path)
    args = parser.parse_args()
    path = args.path or get_settings().excel_input
    try:
        result = inspect_workbook(path)
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"Workbook: {path}")
    print(f"Worksheet: {list(result.worksheet_names)}")
    print(f"Raw Import: {result.raw_import_name}")
    print(f"Header row: {result.header_row}")
    print(f"Columns: {list(result.columns)}")
    print(f"First usable data row: {result.first_data_row}")
    print(f"First empty data row: {result.first_empty_row}")
    print(f"Formula count: {len(result.formula_cells)}")
    print(f"Styled data row count: {len(result.styled_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

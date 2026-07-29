"""External category configuration loader."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from openleadkit.exceptions import CategoryConfigurationError
from openleadkit.schemas import Category


def load_categories(path: Path | None = None) -> list[Category]:
    category_path = path or Path(__file__).resolve().parents[2] / "config" / "categories.json"
    try:
        raw = json.loads(category_path.read_text(encoding="utf-8"))
        categories = TypeAdapter(list[Category]).validate_python(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise CategoryConfigurationError(
            f"Invalid category configuration: {category_path}"
        ) from exc
    keys = [category.key for category in categories]
    if len(keys) != len(set(keys)):
        raise CategoryConfigurationError("Category keys must be unique")
    return categories


def category_by_key(key: str, categories: list[Category] | None = None) -> Category:
    for category in categories or load_categories():
        if category.key == key:
            return category
    raise CategoryConfigurationError(f"Category not found: {key}")

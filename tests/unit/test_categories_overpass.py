import json
from pathlib import Path

import pytest

from openleadkit.exceptions import CategoryConfigurationError
from openleadkit.schemas import BoundingBox, Category
from openleadkit.services.categories import category_by_key, load_categories
from openleadkit.services.overpass import (
    build_overpass_query,
    escape_overpass_value,
    query_hash,
)


def test_builtin_categories_are_valid_and_extensible() -> None:
    categories = load_categories()
    assert len(categories) >= 26
    assert category_by_key("dentist", categories).label == "Dentist"


def test_invalid_categories_report_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "categories.json"
    path.write_text(json.dumps([{"key": "Bad Key", "label": "X", "tags": []}]))
    with pytest.raises(CategoryConfigurationError):
        load_categories(path)


def test_duplicate_category_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "categories.json"
    item = {"key": "cafe", "label": "Cafe", "tags": [{"amenity": "cafe"}]}
    path.write_text(json.dumps([item, item]))
    with pytest.raises(CategoryConfigurationError, match="unique"):
        load_categories(path)


def test_bounding_box_validation_and_area() -> None:
    bbox = BoundingBox(south=-6.3, west=106.7, north=-6.1, east=106.9)
    assert bbox.query_value == "-6.3000000,106.7000000,-6.1000000,106.9000000"
    assert bbox.approximate_area_km2 > 400
    with pytest.raises(ValueError):
        BoundingBox(south=-10, west=100, north=1, east=110)
    with pytest.raises(ValueError):
        BoundingBox(south=1, west=2, north=0, east=3)


def test_overpass_query_supports_all_osm_types_and_hash_is_stable() -> None:
    category = Category(
        key="clinic",
        label="Clinic",
        tags=[{"amenity": "clinic"}, {"healthcare": "clinic"}],
    )
    bbox = BoundingBox(south=-6.3, west=106.7, north=-6.1, east=106.9)
    query = build_overpass_query(category, bbox, 100, require_phone=True, require_website=True)
    assert "node" in query and "way" in query and "relation" in query
    assert "out center tags 100" in query
    assert query_hash(query) == query_hash(query)
    assert len(query_hash(query)) == 64


def test_overpass_escaping_and_limit() -> None:
    assert escape_overpass_value('a"b\\c\n') == 'a\\"b\\\\c '
    with pytest.raises(ValueError):
        escape_overpass_value("x" * 201)
    category = Category(key="cafe", label="Cafe", tags=[{"amenity": "cafe"}])
    bbox = BoundingBox(south=0, west=0, north=1, east=1)
    with pytest.raises(ValueError):
        build_overpass_query(category, bbox, 0)

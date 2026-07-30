import folium
import pytest

from openleadkit.schemas import BoundingBox
from openleadkit.ui import map_selector
from openleadkit.ui.map_selector import (
    extract_latest_rectangle_bounds,
    extract_rectangle_bounds,
)


def test_extract_rectangle_bounds_from_geojson_feature() -> None:
    drawing = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [106.7, -6.3],
                    [107.0, -6.3],
                    [107.0, -6.1],
                    [106.7, -6.1],
                    [106.7, -6.3],
                ]
            ],
        },
    }

    assert extract_rectangle_bounds(drawing) == {
        "south": -6.3,
        "west": 106.7,
        "north": -6.1,
        "east": 107.0,
    }


def test_extract_rectangle_bounds_rejects_non_polygon_geometry() -> None:
    drawing = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [106.8, -6.2]},
    }

    assert extract_rectangle_bounds(drawing) is None


def test_extract_rectangle_bounds_rejects_incomplete_polygon() -> None:
    drawing = {
        "type": "Polygon",
        "coordinates": [[[106.7, -6.3], [107.0, -6.3], ["invalid", -6.1]]],
    }

    assert extract_rectangle_bounds(drawing) is None


def test_extract_rectangle_bounds_normalizes_leaflet_world_copy() -> None:
    drawing = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [1186.76342, -6.3],
                    [1186.833458, -6.3],
                    [1186.833458, -6.1],
                    [1186.76342, -6.1],
                    [1186.76342, -6.3],
                ]
            ],
        },
    }

    assert extract_rectangle_bounds(drawing) == pytest.approx(
        {
            "south": -6.3,
            "west": 106.76342,
            "north": -6.1,
            "east": 106.833458,
        }
    )


def test_extract_latest_rectangle_bounds_uses_only_the_last_drawing() -> None:
    first = {
        "type": "Polygon",
        "coordinates": [
            [[100.0, -7.0], [101.0, -7.0], [101.0, -6.0], [100.0, -6.0], [100.0, -7.0]]
        ],
    }
    latest = {
        "type": "Polygon",
        "coordinates": [
            [[107.0, -6.5], [107.2, -6.5], [107.2, -6.3], [107.0, -6.3], [107.0, -6.5]]
        ],
    }

    assert extract_latest_rectangle_bounds([first, latest]) == {
        "south": -6.5,
        "west": 107.0,
        "north": -6.3,
        "east": 107.2,
    }


def test_render_map_includes_location_and_rectangle_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, folium.MacroElement] = {}

    def fake_st_folium(
        figure: folium.MacroElement,
        **_kwargs: object,
    ) -> dict[str, object]:
        captured["figure"] = figure
        return {"all_drawings": []}

    monkeypatch.setattr(map_selector, "st_folium", fake_st_folium)

    result = map_selector.render_bounding_box_map(
        BoundingBox(south=-6.3, west=106.7, north=-6.1, east=107.0)
    )
    rendered_map = captured["figure"].get_root().render()

    assert result is None
    assert "L.control.locate" in rendered_map
    assert "Go to my current location" in rendered_map
    assert '"rectangle": {' in rendered_map

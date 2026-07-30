"""Interactive map helpers for selecting a validated search bounding box."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import floor
from typing import Any

import folium
from folium.plugins import Draw, LocateControl
from streamlit_folium import st_folium

from openleadkit.schemas import BoundingBox


def _normalize_world_copy_longitudes(longitudes: list[float]) -> list[float] | None:
    """Shift one Leaflet world copy into the canonical longitude range."""
    if not longitudes:
        return None
    offset = 360 * floor((min(longitudes) + 180) / 360)
    normalized = [longitude - offset for longitude in longitudes]
    if not all(-180 <= longitude <= 180 for longitude in normalized):
        return None
    return normalized


def extract_rectangle_bounds(drawing: object) -> dict[str, float] | None:
    """Return South/West/North/East values from a GeoJSON polygon drawing."""
    if not isinstance(drawing, Mapping):
        return None

    geometry: object = drawing.get("geometry", drawing)
    if not isinstance(geometry, Mapping) or geometry.get("type") != "Polygon":
        return None

    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, Sequence) or isinstance(coordinates, (str, bytes)):
        return None

    points: list[tuple[float, float]] = []
    for ring in coordinates:
        if not isinstance(ring, Sequence) or isinstance(ring, (str, bytes)):
            continue
        for point in ring:
            if not isinstance(point, Sequence) or isinstance(point, (str, bytes)) or len(point) < 2:
                continue
            longitude, latitude = point[0], point[1]
            if isinstance(longitude, bool) or isinstance(latitude, bool):
                continue
            if not isinstance(longitude, (int, float)) or not isinstance(latitude, (int, float)):
                continue
            points.append((float(longitude), float(latitude)))

    if len(points) < 4:
        return None

    longitudes, latitudes = zip(*points, strict=True)
    normalized_longitudes = _normalize_world_copy_longitudes(list(longitudes))
    if normalized_longitudes is None or not all(-90 <= latitude <= 90 for latitude in latitudes):
        return None
    return {
        "south": min(latitudes),
        "west": min(normalized_longitudes),
        "north": max(latitudes),
        "east": max(normalized_longitudes),
    }


def extract_latest_rectangle_bounds(drawings: object) -> dict[str, float] | None:
    """Return bounds from only the most recently drawn GeoJSON rectangle."""
    if not isinstance(drawings, Sequence) or isinstance(drawings, (str, bytes)) or not drawings:
        return None
    return extract_rectangle_bounds(drawings[-1])


def render_bounding_box_map(
    bounding_box: BoundingBox,
    *,
    key: str = "bounding_box_map",
) -> dict[str, float] | None:
    """Render a rectangle drawing map and return the latest valid drawing."""
    center = (
        (bounding_box.south + bounding_box.north) / 2,
        (bounding_box.west + bounding_box.east) / 2,
    )
    map_view = folium.Map(
        location=center,
        tiles="OpenStreetMap",
        control_scale=True,
        zoom_start=11,
    )
    map_view.fit_bounds(
        [
            [bounding_box.south, bounding_box.west],
            [bounding_box.north, bounding_box.east],
        ],
        padding=(28, 28),
    )
    folium.Rectangle(
        bounds=[
            [bounding_box.south, bounding_box.west],
            [bounding_box.north, bounding_box.east],
        ],
        color="#246b49",
        fill=True,
        fill_color="#246b49",
        fill_opacity=0.12,
        weight=2,
        tooltip="Current search boundary",
    ).add_to(map_view)
    LocateControl(
        auto_start=False,
        position="bottomright",
        flyTo=True,
        keepCurrentZoomLevel=False,
        showPopup=True,
        strings={
            "title": "Go to my current location",
            "popup": "Your current location",
            "outsideMapBoundsMsg": "Your location is outside the visible map area.",
        },
        locateOptions={"enableHighAccuracy": True},
    ).add_to(map_view)
    Draw(
        export=False,
        position="topleft",
        draw_options={
            "polyline": False,
            "polygon": False,
            "circle": False,
            "marker": False,
            "circlemarker": False,
            "rectangle": {
                "shapeOptions": {
                    "color": "#174f35",
                    "fillColor": "#246b49",
                    "fillOpacity": 0.18,
                    "weight": 2,
                },
                "repeatMode": False,
            },
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(map_view)

    output: dict[str, Any] = st_folium(
        map_view,
        key=key,
        height=460,
        use_container_width=True,
        returned_objects=["all_drawings"],
    )
    return extract_latest_rectangle_bounds(output.get("all_drawings"))

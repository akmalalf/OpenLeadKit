"""Interactive map helpers for selecting a validated search bounding box."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import folium
from folium.plugins import Draw, LocateControl
from streamlit_folium import st_folium

from openleadkit.schemas import BoundingBox


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
    return {
        "south": min(latitudes),
        "west": min(longitudes),
        "north": max(latitudes),
        "east": max(longitudes),
    }


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
        returned_objects=["last_active_drawing"],
    )
    return extract_rectangle_bounds(output.get("last_active_drawing"))

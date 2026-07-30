"""Area lookup, query preview, and user-triggered search page."""

from __future__ import annotations

import streamlit as st

from openleadkit.schemas import BoundingBox
from openleadkit.services.area_lookup import (
    AreaLookupClient,
    cache_selected_area,
    cached_area,
)
from openleadkit.services.categories import load_categories
from openleadkit.services.overpass import build_overpass_query, query_hash
from openleadkit.services.search import recent_completed_search, run_search
from openleadkit.ui.common import (
    db_session,
    format_error,
    load_settings_or_stop,
    section_header,
    setup_page,
)
from openleadkit.ui.map_selector import render_bounding_box_map

DEFAULT_BOUNDING_BOX = {
    "south": -0.1,
    "west": -0.1,
    "north": 0.1,
    "east": 0.1,
}
BOUNDING_BOX_KEYS = {
    "south": "bbox_south",
    "west": "bbox_west",
    "north": "bbox_north",
    "east": "bbox_east",
}


def _set_bounding_box_state(values: dict[str, float]) -> None:
    normalized = {name: float(values[name]) for name in BOUNDING_BOX_KEYS}
    st.session_state.bbox = normalized
    for name, widget_key in BOUNDING_BOX_KEYS.items():
        st.session_state[widget_key] = normalized[name]


def _initialize_bounding_box_state() -> None:
    stored = st.session_state.get("bbox", DEFAULT_BOUNDING_BOX)
    for name, widget_key in BOUNDING_BOX_KEYS.items():
        if widget_key not in st.session_state:
            st.session_state[widget_key] = float(stored[name])


def _reset_map_component() -> None:
    st.session_state.bounding_box_map_revision = (
        int(st.session_state.get("bounding_box_map_revision", 0)) + 1
    )


@st.dialog("How to use Business Search", width="large")
def _show_search_guide() -> None:
    st.markdown(
        """
        Business Search creates one geographically bounded request to OpenStreetMap.
        Follow these steps:

        **1. Choose a business category**

        Select the type of business you want to discover.

        **2. Define the search area**

        Search for an area name and choose **Use Bounding Box**, draw one rectangle
        on the map, or enter the four coordinates manually. The optional location
        target centers the map after you grant browser permission; it does not select
        an area by itself. Check the estimated area before continuing.

        **3. Set the result limit**

        Start with a modest limit. Enable phone or website requirements only when
        those fields are essential, because they can reduce the number of matches.

        **4. Review the request**

        **Preview query** shows the generated read-only Overpass request. It does not
        contact the public service.

        **5. Start the search**

        **Start search** sends the request and saves completed results to PostgreSQL.
        Open **Search Results** afterward to filter and download the saved leads.
        """
    )
    st.info(
        "Nothing is requested automatically. OpenLeadKit contacts Overpass only after "
        "you press Start search."
    )
    if st.button("Close guide", type="primary", use_container_width=True):
        st.rerun()


def render() -> None:
    if setup_page(
        "Area-based discovery",
        "Business Search",
        "Select a category and bound the geographic area. Requests run only after you "
        "press the search button.",
        action_label="How to use",
        action_key="business_search_guide",
    ):
        _show_search_guide()
    settings = load_settings_or_stop()
    categories = load_categories()
    labels = {category.label: category for category in categories}
    section_header(
        "Choose a market",
        "Select a business category, then resolve an area name or enter coordinates manually.",
        "STEP 01",
    )
    category_label = st.selectbox("Business category", labels)
    category = labels[category_label]
    area_name = st.text_input(
        "Area name", max_chars=300, placeholder="Example: London, United Kingdom"
    )
    country_codes = st.text_input(
        "Country codes (optional)",
        max_chars=200,
        placeholder="Comma-separated ISO codes, for example: gb,ie",
    )
    if st.button("Search Area", disabled=not area_name):
        try:
            with db_session() as lookup_session:
                cached = cached_area(lookup_session, area_name, country_codes=country_codes or None)
            if cached:
                st.session_state.area_results = [cached]
                st.info("Area results loaded from the cache.")
            else:
                st.session_state.area_results = AreaLookupClient(settings).search(
                    area_name, country_codes=country_codes or None
                )
        except Exception as exc:
            st.error(format_error(exc))
    results = st.session_state.get("area_results", [])
    if results:
        choices = {result.display_name: result for result in results}
        selected_name = st.selectbox(
            "Select an area result (no automatic selection)", ["", *list(choices)]
        )
        if selected_name and st.button("Use Bounding Box"):
            selected = choices[selected_name]
            st.session_state.selected_area_name = selected.display_name
            st.session_state.boundary_source = "area"
            _set_bounding_box_state(selected.bounding_box.model_dump())
            _reset_map_component()
            with db_session() as cache_session:
                cache_selected_area(
                    cache_session,
                    area_name,
                    selected,
                    country_codes=country_codes or None,
                )
            st.success("The bounding box was selected and the area result was cached.")
    _initialize_bounding_box_state()
    section_header(
        "Set the search boundary",
        "Draw one rectangle on the map or enter coordinates. The boundary is limited "
        "to 5° per side.",
        "STEP 02",
    )
    try:
        current_bbox = BoundingBox(
            south=st.session_state[BOUNDING_BOX_KEYS["south"]],
            west=st.session_state[BOUNDING_BOX_KEYS["west"]],
            north=st.session_state[BOUNDING_BOX_KEYS["north"]],
            east=st.session_state[BOUNDING_BOX_KEYS["east"]],
        )
    except ValueError:
        current_bbox = BoundingBox(**DEFAULT_BOUNDING_BOX)

    map_tab, coordinates_tab = st.tabs(["Draw on map", "Enter coordinates"])
    with map_tab:
        if st.session_state.pop("map_boundary_applied_notice", False):
            st.success(
                "Boundary applied from the map. The green rectangle is the active search boundary."
            )
        st.markdown(
            """
            **Select the search area**

            1. Optionally click the **location target** at the bottom-right to center
               the map on your current position.
            2. Click the **rectangle tool** at the top-left.
            3. Drag one rectangle over the area you want to search. The pale green
               rectangle shows the boundary currently in use. If you draw again,
               only the newest rectangle is applied.
            """
        )
        st.caption(
            "Location access is requested only when you click the target. It centers "
            "the map but does not save a boundary or start a search."
        )
        map_revision = int(st.session_state.get("bounding_box_map_revision", 0))
        drawn_bounds = render_bounding_box_map(
            current_bbox,
            key=f"bounding_box_map_{map_revision}",
        )
        if drawn_bounds is not None:
            try:
                drawn_bbox = BoundingBox(**drawn_bounds)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop("selected_area_name", None)
                st.session_state.boundary_source = "map"
                _set_bounding_box_state(drawn_bbox.model_dump())
                _reset_map_component()
                st.session_state.map_boundary_applied_notice = True
                st.rerun()
        st.caption(
            "If the location button is unavailable, allow location permission in your "
            "browser or use area search above. Deployed sites require HTTPS for location access."
        )

    with coordinates_tab:
        st.caption("Use decimal degrees. South must be below North, and West must be left of East.")
        columns = st.columns(4)
        south = columns[0].number_input(
            "South",
            key=BOUNDING_BOX_KEYS["south"],
            format="%.7f",
        )
        west = columns[1].number_input(
            "West",
            key=BOUNDING_BOX_KEYS["west"],
            format="%.7f",
        )
        north = columns[2].number_input(
            "North",
            key=BOUNDING_BOX_KEYS["north"],
            format="%.7f",
        )
        east = columns[3].number_input(
            "East",
            key=BOUNDING_BOX_KEYS["east"],
            format="%.7f",
        )

    entered_bbox = {
        "south": float(south),
        "west": float(west),
        "north": float(north),
        "east": float(east),
    }
    if entered_bbox != st.session_state.get("bbox"):
        st.session_state.pop("selected_area_name", None)
        st.session_state.boundary_source = "manual"
    st.session_state.bbox = entered_bbox
    maximum_results = st.number_input(
        "Maximum results",
        min_value=1,
        max_value=settings.max_result_limit,
        value=settings.default_result_limit,
    )
    require_phone = st.checkbox("Require a phone number")
    require_website = st.checkbox("Require a website")
    try:
        bbox = BoundingBox(south=south, west=west, north=north, east=east)
        st.caption(f"Estimated bounding-box area: {bbox.approximate_area_km2:,.1f} km²")
        query = build_overpass_query(
            category,
            bbox,
            int(maximum_results),
            require_phone=require_phone,
            require_website=require_website,
        )
    except ValueError as exc:
        st.error(str(exc))
        return
    section_header(
        "Review and run",
        "Confirm the summary below. Preview the generated request or open the guide "
        "if this is your first search.",
        "STEP 03",
    )

    selected_area = st.session_state.get("selected_area_name")
    boundary_source = st.session_state.get("boundary_source", "manual")
    area_summary = (
        selected_area
        if selected_area
        else "Map rectangle"
        if boundary_source == "map"
        else "Manual coordinates"
    )
    if require_phone and require_website:
        contact_filter = "Phone and website"
    elif require_phone:
        contact_filter = "Phone required"
    elif require_website:
        contact_filter = "Website required"
    else:
        contact_filter = "No contact filter"

    with st.container(border=True):
        summary_columns = st.columns([1.4, 1.2, 1, 1])
        summary_columns[0].caption("CATEGORY")
        summary_columns[0].write(f"**{category.label}**")
        summary_columns[1].caption("AREA")
        summary_columns[1].write(f"**{area_summary}**")
        summary_columns[2].caption("ESTIMATED SIZE")
        summary_columns[2].write(f"**{bbox.approximate_area_km2:,.1f} km²**")
        summary_columns[3].caption("RESULT CAP")
        summary_columns[3].write(f"**{int(maximum_results):,}**")
        st.caption(f"Contact requirements: {contact_filter}")
        st.divider()

        preview, start = st.columns([1, 1.35])
        show_preview = preview.button("Preview query", use_container_width=True)
        start_search = start.button(
            "Start search",
            type="primary",
            use_container_width=True,
        )
        st.caption(
            "No public request is sent until you press Start search. "
            "Completed results are saved before they appear in Search Results."
        )

    if show_preview:
        st.code(query, language="text")
    with db_session() as session:
        if previous := recent_completed_search(session, query_hash(query)):
            st.warning(
                f"An identical search completed recently at {previous.finished_at}. "
                "You can still run it again."
            )
        if start_search:
            with st.status("Contacting Overpass and saving results…", expanded=True) as status:
                result = run_search(
                    session,
                    settings,
                    category,
                    bbox,
                    area_query=selected_area or area_summary,
                    area_display_name=selected_area,
                    maximum_results=int(maximum_results),
                    require_phone=require_phone,
                    require_website=require_website,
                )
                if result.status.value == "Completed":
                    status.update(label="Search completed and saved", state="complete")
                    st.success(
                        f"Received {result.total_received}; created {result.total_created}; "
                        f"updated {result.total_updated}; duplicate candidates "
                        f"{result.total_possible_duplicates}."
                    )
                else:
                    status.update(label="Search failed", state="error")
                    st.error(result.error_message or "No failure reason is available")
    st.caption("Data © OpenStreetMap contributors, available under the ODbL.")

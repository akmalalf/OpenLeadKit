"""Filterable, pageable business result view."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from openleadkit.repositories import LeadViewRepository
from openleadkit.ui.common import (
    db_session,
    empty_state,
    section_header,
    setup_page,
)


def render() -> None:
    setup_page(
        "Lead database",
        "Search Results",
        "Filter and download the current view as CSV. CSV downloads do not change lead status.",
    )
    with db_session() as session:
        businesses = LeadViewRepository(session).all_businesses()
    if not businesses:
        empty_state(
            "No lead data yet",
            "Run your first search from Business Search. Saved businesses will appear here.",
            "00",
        )
        return
    run_options = {
        f"{association.search_run.created_at:%Y-%m-%d %H:%M} · "
        f"{association.search_run.category_label} · {association.search_run.area_query}": (
            association.search_run.id
        )
        for item in businesses
        for association in item.search_runs
    }
    with st.expander(f"Filter records · {len(businesses)} total", expanded=True):
        st.caption(
            "Choose one or more conditions, then press Apply filters. "
            "Saved lead data will not be changed."
        )
        with st.form("result_filters", clear_on_submit=False):
            query = st.text_input(
                "Search name, city, district, or address",
                max_chars=200,
            ).casefold()
            left, middle, right = st.columns(3)
            categories = left.multiselect(
                "Category",
                sorted({item.category_label for item in businesses}),
            )
            cities = middle.multiselect(
                "City",
                sorted({item.city for item in businesses if item.city}),
            )
            districts = right.multiselect(
                "District",
                sorted({item.district for item in businesses if item.district}),
            )
            left, middle, right = st.columns(3)
            areas = left.multiselect(
                "Search area",
                sorted(
                    {
                        association.search_run.area_display_name
                        or association.search_run.area_query
                        for item in businesses
                        for association in item.search_runs
                    }
                ),
            )
            selected_runs = middle.multiselect("Search history", list(run_options))
            reviews = right.multiselect(
                "Review status",
                sorted({item.review_status.value for item in businesses}),
            )
            left, middle, right = st.columns(3)
            qualifications = left.multiselect(
                "Qualification",
                sorted({item.qualification_status.value for item in businesses}),
            )
            has_phone = middle.selectbox("Phone", ["All", "Available", "Missing"])
            has_website = right.selectbox("Website", ["All", "Available", "Missing"])
            left, right = st.columns(2)
            first_seen_since = left.date_input(
                "First seen since",
                value=date.today() - timedelta(days=365),
            )
            last_seen_until = right.date_input("Last seen through", value=date.today())
            st.form_submit_button("Apply filters", type="primary")
    selected_run_ids = {run_options[label] for label in selected_runs}
    rows = []
    for item in businesses:
        item_areas = {
            association.search_run.area_display_name or association.search_run.area_query
            for association in item.search_runs
        }
        item_run_ids = {association.search_run_id for association in item.search_runs}
        haystack = " ".join(
            value or "" for value in (item.business_name, item.city, item.district, item.address)
        ).casefold()
        if query and query not in haystack:
            continue
        if categories and item.category_label not in categories:
            continue
        if cities and item.city not in cities:
            continue
        if districts and item.district not in districts:
            continue
        if areas and not item_areas.intersection(areas):
            continue
        if selected_run_ids and not item_run_ids.intersection(selected_run_ids):
            continue
        if reviews and item.review_status.value not in reviews:
            continue
        if qualifications and item.qualification_status.value not in qualifications:
            continue
        if has_phone != "All" and bool(item.phone) != (has_phone == "Available"):
            continue
        if has_website != "All" and bool(item.website_url) != (has_website == "Available"):
            continue
        if item.first_seen_at.date() < first_seen_since:
            continue
        if item.last_seen_at.date() > last_seen_until:
            continue
        rows.append(
            {
                "Business Name": item.business_name,
                "Category": item.category_label,
                "City": item.city,
                "District": item.district,
                "Phone": item.phone,
                "Website": item.website_url,
                "Review": item.review_status.value,
                "Qualification": item.qualification_status.value,
                "Search Area": ", ".join(sorted(item_areas)),
                "First Seen": item.first_seen_at,
                "Last Seen": item.last_seen_at,
            }
        )
    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        empty_state(
            "No matching records",
            "Broaden one or more filters to bring leads back into view.",
            "0",
        )
        return
    section_header(
        "Result table",
        "Choose the sort order, visible columns, and page size before downloading.",
        f"{len(dataframe)} MATCHES",
    )
    sort_column = st.selectbox("Sort by", list(dataframe.columns), index=9)
    descending = st.checkbox("Descending order", value=True)
    dataframe = dataframe.sort_values(sort_column, ascending=not descending)
    selected_columns = st.multiselect(
        "Displayed columns",
        list(dataframe.columns),
        default=list(dataframe.columns),
    )
    if not selected_columns:
        st.warning("Select at least one column.")
        return
    page_size = st.selectbox("Rows per page", [10, 25, 50, 100], index=1)
    page_count = max(1, (len(dataframe) + page_size - 1) // page_size)
    page = st.number_input("Page", min_value=1, max_value=page_count, value=1)
    start = (int(page) - 1) * page_size
    st.dataframe(
        dataframe.loc[:, selected_columns].iloc[start : start + page_size],
        width="stretch",
    )
    st.caption(f"{len(dataframe)} results · page {page} of {page_count}")
    st.download_button(
        "Download this view as CSV",
        dataframe.to_csv(index=False).encode("utf-8-sig"),
        file_name="openleadkit_filtered_results.csv",
        mime="text/csv",
    )

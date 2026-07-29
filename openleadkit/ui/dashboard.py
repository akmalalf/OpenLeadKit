"""Dashboard page."""

from __future__ import annotations

from datetime import UTC
from html import escape

import streamlit as st

from openleadkit.models import SearchRun
from openleadkit.repositories import LeadViewRepository
from openleadkit.ui.common import (
    db_session,
    empty_state,
    metric_grid,
    section_header,
    setup_page,
)


def _render_recent_searches(searches: tuple[SearchRun, ...]) -> None:
    rows: list[str] = []
    for index, search in enumerate(searches, start=1):
        area = search.area_display_name or search.area_query
        completed_at = search.finished_at or search.created_at
        completed_utc = completed_at.astimezone(UTC)
        rows.append(
            "<tr>"
            f'<td class="olk-search-index">{index:02d}</td>'
            f'<td class="olk-search-category">{escape(search.category_label)}</td>'
            f'<td class="olk-search-area">{escape(area)}</td>'
            '<td><span class="olk-search-results">'
            f"<strong>{search.total_created:,}</strong><span>created</span>"
            f"<strong>{search.total_updated:,}</strong><span>updated</span>"
            "</span></td>"
            f'<td><time datetime="{escape(completed_utc.isoformat())}" '
            'class="olk-search-time">'
            f"<strong>{completed_utc.strftime('%d %b %Y')}</strong>"
            f"<span>{completed_utc.strftime('%H:%M')} UTC</span>"
            "</time></td>"
            "</tr>"
        )
    st.markdown(
        (
            '<div class="olk-search-table-wrap">'
            '<table class="olk-search-table">'
            '<caption class="olk-visually-hidden">Five latest completed searches</caption>'
            "<thead><tr>"
            '<th scope="col">#</th>'
            '<th scope="col">Category</th>'
            '<th scope="col">Area</th>'
            '<th scope="col">Results</th>'
            '<th scope="col">Completed</th>'
            "</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render() -> None:
    setup_page(
        "Operations overview",
        "Dashboard",
        "Monitor lead data, review workload, and search health in one place.",
    )
    with db_session() as session:
        snapshot = LeadViewRepository(session).dashboard()
        pipeline_metrics = [
            ("Total businesses", snapshot.total_businesses),
            ("New", snapshot.new),
            ("Reviewed", snapshot.reviewed),
            ("Approved", snapshot.approved),
            ("Exported", snapshot.exported),
        ]
        operational_metrics = [
            ("High priority", snapshot.high_priority),
            ("Pending duplicates", snapshot.pending_duplicates),
            ("Completed searches", snapshot.completed_searches),
            ("Failed searches", snapshot.failed_searches),
        ]
        section_header(
            "Lead pipeline",
            "A live count of records as they move from discovery to CRM export.",
            "CURRENT",
        )
        metric_grid(pipeline_metrics)

        section_header(
            "Operations",
            "Signals that need attention and recent search health.",
            "WORKLOAD",
        )
        metric_grid(operational_metrics)

        last_export = snapshot.last_export
        section_header(
            "Recent activity",
            "The five latest completed searches and the most recent CRM handoff.",
            "AUDIT",
        )
        left, right = st.columns([1.35, 1])
        with left:
            st.subheader("Latest searches")
            if snapshot.recent_searches:
                _render_recent_searches(snapshot.recent_searches)
            else:
                empty_state(
                    "No completed searches",
                    "Open Business Search to discover the first set of local businesses.",
                    "01",
                )
        with right:
            st.subheader("Latest export")
            if last_export:
                st.write(f"Batch `{last_export.batch_id}`")
                st.caption(f"{last_export.exported_count} leads exported")
            else:
                empty_state(
                    "No CRM exports",
                    "Approved leads will appear here after a verified workbook export.",
                    "02",
                )

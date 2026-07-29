"""Operational audit and failure history."""

from __future__ import annotations

import streamlit as st

from openleadkit.repositories import LeadViewRepository
from openleadkit.ui.common import db_session, section_header, setup_page


def render() -> None:
    setup_page(
        "Audit trail",
        "History",
        "Review searches, failures, website checks, duplicate decisions, reviews, and exports.",
    )
    section_header(
        "Recorded events",
        "Switch views to inspect each operational trail. Database credentials are never shown.",
        "READ ONLY",
    )
    tabs = st.tabs(["Searches", "Website Checks", "Reviews", "Duplicates", "Exports"])
    with db_session() as session:
        views = LeadViewRepository(session)
        with tabs[0]:
            search_rows = views.search_history()
            st.dataframe(
                [
                    {
                        "Time": row.created_at,
                        "Category": row.category_label,
                        "Area": row.area_display_name or row.area_query,
                        "Status": row.status.value,
                        "Received": row.total_received,
                        "Created": row.total_created,
                        "Error": row.error_message,
                    }
                    for row in search_rows
                ],
                width="stretch",
            )
        with tabs[1]:
            website_rows = views.website_history()
            st.dataframe(
                [
                    {
                        "Time": row.checked_at or row.created_at,
                        "Business ID": row.business_id,
                        "URL": row.requested_url,
                        "Status": row.status.value,
                        "HTTP": row.http_status,
                        "Error": row.error_message,
                    }
                    for row in website_rows
                ],
                width="stretch",
            )
        with tabs[2]:
            review_rows = views.all_review_events()
            st.dataframe(
                [
                    {
                        "Time": row.created_at,
                        "Business ID": row.business_id,
                        "Type": row.event_type,
                        "Before": row.previous_value,
                        "After": row.new_value,
                        "Notes": row.notes,
                    }
                    for row in review_rows
                ],
                width="stretch",
            )
        with tabs[3]:
            duplicate_rows = views.duplicate_history()
            st.dataframe(
                [
                    {
                        "Time": row.created_at,
                        "Left": row.business_id,
                        "Right": row.candidate_business_id,
                        "Reason": row.match_type.value,
                        "Score": row.similarity_score,
                        "Status": row.status.value,
                        "Notes": row.decision_notes,
                    }
                    for row in duplicate_rows
                ],
                width="stretch",
            )
        with tabs[4]:
            export_rows = views.export_history()
            st.dataframe(
                [
                    {
                        "Time": row.exported_at or row.created_at,
                        "Batch": row.batch_id,
                        "Status": row.status.value,
                        "Exported": row.exported_count,
                        "Skipped": row.skipped_existing_count,
                        "Output": row.workbook_output,
                        "Error": row.error_message,
                    }
                    for row in export_rows
                ],
                width="stretch",
            )

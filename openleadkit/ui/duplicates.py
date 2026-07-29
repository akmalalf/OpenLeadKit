"""Duplicate candidate comparison and confirmed merge."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from openleadkit.models import Business, DuplicateStatus
from openleadkit.repositories import LeadRepository, LeadViewRepository
from openleadkit.ui.common import (
    commit_and_rerun,
    db_session,
    empty_state,
    section_header,
    setup_page,
)


def _display_value(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return str(value)


def _business_fields(business: Business) -> dict[str, str]:
    return {
        "Name": _display_value(business.business_name),
        "City": _display_value(business.city),
        "District": _display_value(business.district),
        "Address": _display_value(business.address),
        "Phone": _display_value(business.phone),
        "Domain": _display_value(business.normalized_domain),
        "Website": _display_value(business.website_url),
        "OSM": f"{business.osm_type}/{business.osm_id}",
        "First seen": _display_value(business.first_seen_at),
    }


def render() -> None:
    setup_page(
        "Quality control",
        "Duplicates",
        "Compare candidates side by side. Similar names are never merged automatically.",
    )
    with db_session() as session:
        views = LeadViewRepository(session)
        candidates = views.pending_duplicate_candidates()
        if not candidates:
            empty_state(
                "Duplicate queue is clear",
                "New candidates will appear here when matching rules find records that need "
                "a manual decision.",
                "✓",
            )
            return
        section_header(
            "Candidate comparison",
            "Review the match signal and source fields before choosing an action.",
            f"{len(candidates)} PENDING",
        )
        labels = {
            (
                f"{candidate.match_type.value} · "
                f"{candidate.similarity_score or 0:.0%} · {candidate.id}"
            ): candidate
            for candidate in candidates
        }
        selected = labels[st.selectbox("Select a pair", labels)]
        left = views.business(selected.business_id)
        right = views.business(selected.candidate_business_id)
        if not left or not right:
            st.error("One of the businesses was not found.")
            return
        st.write(f"**Match reason:** {selected.match_type.value}")
        st.progress(float(selected.similarity_score or 0), text="Similarity score")
        col_left, col_right = st.columns(2)
        col_left.subheader(left.business_name)
        col_left.dataframe(
            [{"Field": key, "Value": value} for key, value in _business_fields(left).items()],
            hide_index=True,
        )
        col_right.subheader(right.business_name)
        col_right.dataframe(
            [{"Field": key, "Value": value} for key, value in _business_fields(right).items()],
            hide_index=True,
        )
        notes = st.text_area("Decision notes", max_chars=2_000)
        repository = LeadRepository(session)
        with st.container(border=True):
            st.subheader("Resolve without merging")
            st.caption("Choose one of these actions when both source records should remain intact.")
            keep_action, ignore_action = st.columns(2)
            keep_action.markdown("**Keep both records**")
            keep_action.caption("Confirm they are separate businesses and close this candidate.")
            ignore_action.markdown("**Ignore this candidate**")
            ignore_action.caption("Dismiss this match without changing either business record.")
            keep_both = keep_action.button(
                "Keep both records",
                icon=":material/done_all:",
                type="primary",
                use_container_width=True,
            )
            ignore_candidate = ignore_action.button(
                "Ignore candidate",
                icon=":material/visibility_off:",
                use_container_width=True,
            )
        if keep_both:
            repository.decide_duplicate(selected, DuplicateStatus.KEEP_BOTH, notes)
            commit_and_rerun(session)
        if ignore_candidate:
            repository.decide_duplicate(selected, DuplicateStatus.IGNORE, notes)
            commit_and_rerun(session)
        section_header(
            "Confirm merge",
            "Choose the surviving record. Merges create an audit snapshot before deletion.",
            "DESTRUCTIVE",
        )
        with st.container(border=True):
            direction = st.radio(
                "Record to keep",
                [f"Left: {left.business_name}", f"Right: {right.business_name}"],
            )
            confirmed = st.checkbox(
                "I understand that the merged record will be deleted after an audit "
                "snapshot is made."
            )
            merge_records = st.button(
                "Merge records",
                icon=":material/merge:",
                disabled=not confirmed,
                type="primary",
                use_container_width=True,
            )
        if merge_records:
            survivor, merged = (left, right) if direction.startswith("Left") else (right, left)
            repository.merge(
                survivor,
                merged,
                reason=notes or f"Duplicate: {selected.match_type.value}",
                merged_by="streamlit-user",
            )
            st.success("The records were merged in one transaction and the audit snapshot saved.")
            commit_and_rerun(session)

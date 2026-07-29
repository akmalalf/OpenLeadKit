"""One-at-a-time lead review workflow."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from openleadkit.config import get_settings
from openleadkit.models import (
    QualificationStatus,
    ReviewStatus,
    WebsiteCheck,
    WebsiteCheckStatus,
)
from openleadkit.repositories import LeadRepository, LeadReviewSort, LeadViewRepository
from openleadkit.services.qualification import (
    QualificationInputs,
    calculate_suggestion,
)
from openleadkit.services.website_checker import WebsiteChecker
from openleadkit.ui.common import (
    commit_and_rerun,
    db_session,
    empty_state,
    format_error,
    section_header,
    setup_page,
)


@st.dialog("How to review a lead", width="large")
def _show_review_guide() -> None:
    st.markdown(
        """
        Review one business at a time and save each decision separately.

        **1. Choose the queue order**

        Use **Sort by** to change the queue order, including the calculated
        **Transparent suggestion score** from highest to lowest. Use
        **Qualification filter** when you want to show only High, Medium, Low,
        Not Qualified, or Unknown leads. Changing either control returns you to
        the first lead.

        **2. Verify the business**

        Check the business name, address, contact details, and OpenStreetMap source.
        Use **Inspect website** only when a stored official website is available.

        **3. Read the quality signals**

        Review duplicate candidates, website-check results, and the transparent
        suggestion score. These signals support your decision but never replace it.

        **4. Decide the review status**

        Choose **Approve** when the record is suitable for the lead workflow, or
        **Reject** when it should not progress.

        **5. Set the qualification**

        Select the appropriate manual qualification level, then save it separately.

        **6. Record useful notes**

        Add concise evidence or context for future reviewers. Every saved change is
        recorded in the audit trail.
        """
    )
    st.info(
        "Approve, reject, qualification, and notes are separate actions so the history "
        "shows exactly what changed."
    )
    if st.button("Close guide", type="primary", use_container_width=True):
        st.rerun()


def _reset_review_index() -> None:
    st.session_state.review_index = 0


def render() -> None:
    if setup_page(
        "Verification queue",
        "Lead Review",
        "Inspect one business at a time. Every status and note change is recorded for audit.",
        action_label="How to use",
        action_key="lead_review_guide",
    ):
        _show_review_guide()

    sort_options = list(LeadReviewSort)
    if st.session_state.get("lead_review_sort") not in (None, *sort_options):
        st.session_state.lead_review_sort = LeadReviewSort.NEEDS_REVIEW

    sort_column, filter_column = st.columns(2)
    sort_by = sort_column.selectbox(
        "Sort by",
        sort_options,
        format_func=lambda option: option.value,
        key="lead_review_sort",
        on_change=_reset_review_index,
    )
    qualification_filter = filter_column.selectbox(
        "Qualification filter",
        [None, *list(QualificationStatus)],
        format_func=lambda option: "All qualifications" if option is None else option.value,
        key="lead_review_qualification_filter",
        on_change=_reset_review_index,
    )
    st.caption(
        "Sort changes the order. Qualification filter limits which leads appear. "
        "Both controls run in the database and return you to the first lead."
    )

    with db_session() as session:
        views = LeadViewRepository(session)
        ids = views.business_ids(sort_by, qualification_filter)
        if not ids:
            empty_title = (
                f"No {qualification_filter.value} leads found"
                if qualification_filter is not None
                else "Review queue is empty"
            )
            empty_state(
                empty_title,
                "Choose another qualification filter or run a business search to add leads.",
                "✓",
            )
            return
        index = min(st.session_state.get("review_index", 0), len(ids) - 1)
        business = views.business(ids[index])
        if business is None:
            st.error("The lead was not found.")
            return
        section_header(
            business.business_name,
            f"{business.category_label} · {business.city or 'Location unavailable'}",
            f"{index + 1:02d} / {len(ids):02d}",
        )
        left, right = st.columns([1.25, 1])
        with left:
            st.write(f"**Category:** {business.category_label}")
            st.write(f"**Address:** {business.address or '—'}")
            st.write(f"**City / district:** {business.city or '—'} / {business.district or '—'}")
            st.write(f"**Phone:** {business.phone or '—'}")
            st.write(f"**Website:** {business.website_url or '—'}")
            st.write(f"**Instagram:** {business.instagram or '—'}")
            st.write(f"**Opening hours:** {business.opening_hours or '—'}")
            st.link_button("Open OpenStreetMap source", business.source_url)
            st.caption(f"Coordinates {business.latitude:.7f}, {business.longitude:.7f}")
        with right:
            st.metric("Review status", business.review_status.value)
            st.metric("Qualification", business.qualification_status.value)
            duplicate_count = len(views.duplicates_for_business(business.id))
            st.write(f"**Duplicate candidates:** {duplicate_count}")
            latest_check = views.latest_website_check(business.id)
            if latest_check:
                st.write(f"**Website check:** {latest_check.status.value}")
                st.caption(latest_check.page_title or latest_check.error_message or "")
            suggestion = calculate_suggestion(
                QualificationInputs(
                    has_website=bool(business.website_url),
                    website_available=(
                        latest_check.http_status < 400
                        if latest_check and latest_check.http_status is not None
                        else None
                    ),
                    has_phone=bool(business.phone),
                    has_public_email=bool(
                        business.email or (latest_check and latest_check.public_email)
                    ),
                    mobile_viewport_found=(
                        latest_check.mobile_viewport_found if latest_check else None
                    ),
                    https_enabled=latest_check.https_enabled if latest_check else None,
                    contact_page_found=bool(latest_check and latest_check.contact_page_url),
                    complete_address=bool(business.address and business.city),
                    search_count=len(business.search_runs),
                )
            )
            st.metric("Transparent suggestion score", f"{suggestion.score}/100")
            with st.expander("Score explanation"):
                if suggestion.explanation:
                    for reason in suggestion.explanation:
                        st.write(reason)
                else:
                    st.caption("No signals currently add to the score.")
        repository = LeadRepository(session)
        section_header(
            "Review actions",
            "Save each decision separately so the audit trail stays clear.",
            "MANUAL",
        )
        with st.container(border=True):
            st.subheader("Review status")
            st.caption("Decide whether this lead can continue through the workflow.")
            action_columns = st.columns(2)
            if action_columns[0].button(
                "Approve",
                type="primary",
                use_container_width=True,
            ):
                repository.update_review(business, review_status=ReviewStatus.APPROVED)
                commit_and_rerun(session)
            if action_columns[1].button("Reject", use_container_width=True):
                repository.update_review(business, review_status=ReviewStatus.REJECTED)
                commit_and_rerun(session)

            st.divider()
            st.subheader("Manual qualification")
            qualification_input, qualification_action = st.columns(
                [2, 1],
                vertical_alignment="bottom",
            )
            qualification = qualification_input.selectbox(
                "Qualification level",
                list(QualificationStatus),
                format_func=lambda item: item.value,
                index=list(QualificationStatus).index(business.qualification_status),
            )
            if qualification_action.button(
                "Save qualification",
                use_container_width=True,
            ):
                repository.update_review(business, qualification_status=qualification)
                commit_and_rerun(session)

            st.divider()
            st.subheader("Notes and verification")
            st.caption("Record evidence for the next reviewer or inspect the official website.")
            notes = st.text_area(
                "Review notes",
                value=business.raw_notes or "",
                max_chars=5_000,
            )
            note_action, website_action = st.columns(2)
            if note_action.button("Save notes", use_container_width=True):
                repository.update_review(business, notes=notes)
                commit_and_rerun(session)
            inspect_website = website_action.button(
                "Inspect website",
                disabled=not business.website_url,
                use_container_width=True,
            )
            st.caption(
                "Each saved decision is handled separately to keep the audit history precise."
            )

        if inspect_website:
            pending = WebsiteCheck(
                business_id=business.id,
                requested_url=business.website_url or "",
                status=WebsiteCheckStatus.PENDING,
            )
            session.add(pending)
            session.flush()
            try:
                inspection = WebsiteChecker(get_settings()).inspect(business.website_url or "")
                pending.checked_url = business.website_url
                pending.final_url = inspection.final_url
                pending.http_status = inspection.http_status
                pending.content_type = inspection.content_type
                pending.response_bytes = inspection.response_bytes
                pending.page_title = inspection.fields.title
                pending.https_enabled = inspection.https_enabled
                pending.mobile_viewport_found = inspection.fields.mobile_viewport_found
                pending.contact_page_url = inspection.fields.contact_page_url
                pending.about_page_url = inspection.fields.about_page_url
                pending.public_email = inspection.fields.public_email
                pending.public_phone = inspection.fields.public_phone
                pending.whatsapp_url = inspection.fields.whatsapp_url
                pending.instagram_url = inspection.fields.instagram_url
                pending.robots_allowed = inspection.robots_allowed
                pending.status = WebsiteCheckStatus.COMPLETED
                pending.checked_at = datetime.now(UTC)
                st.success("Website inspection completed.")
            except Exception as exc:
                pending.status = WebsiteCheckStatus.BLOCKED
                pending.error_type = type(exc).__name__
                pending.error_message = str(exc)
                pending.checked_at = datetime.now(UTC)
                st.error(format_error(exc))
        events = views.review_events(business.id)
        with st.expander("Change history"):
            if events:
                st.dataframe(
                    [
                        {
                            "Time": event.created_at,
                            "Type": event.event_type,
                            "Before": event.previous_value,
                            "After": event.new_value,
                            "Notes": event.notes,
                        }
                        for event in events
                    ],
                    width="stretch",
                )
            else:
                st.caption("No review events yet.")
    with st.container(border=True):
        previous, position, next_button = st.columns(
            [1, 0.65, 1],
            vertical_alignment="center",
        )
        go_previous = previous.button(
            "Previous lead",
            icon=":material/arrow_back:",
            disabled=index == 0,
            use_container_width=True,
        )
        position.markdown(
            (
                '<div class="olk-pager-status">'
                f"<strong>{index + 1} / {len(ids)}</strong>"
                "<span>Queue position</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        go_next = next_button.button(
            "Next lead",
            icon=":material/arrow_forward:",
            icon_position="right",
            type="primary",
            disabled=index >= len(ids) - 1,
            use_container_width=True,
        )
    if go_previous:
        st.session_state.review_index = index - 1
        st.rerun()
    if go_next:
        st.session_state.review_index = index + 1
        st.rerun()

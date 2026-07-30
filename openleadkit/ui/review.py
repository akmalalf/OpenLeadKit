"""One-at-a-time lead review workflow."""

from __future__ import annotations

import uuid

import streamlit as st
from pydantic import ValidationError

from openleadkit.models import QualificationStatus, ReviewStatus
from openleadkit.repositories import LeadRepository, LeadReviewSort, LeadViewRepository
from openleadkit.services.normalization import normalize_url
from openleadkit.services.qualification import (
    QualificationInputs,
    calculate_suggestion,
)
from openleadkit.services.review import LeadReviewDetails
from openleadkit.ui.common import (
    db_session,
    empty_state,
    safe_validation_error,
    section_header,
    setup_page,
)

_REVIEW_DRAFT_FIELDS = (
    "business_name",
    "website_url",
    "phone",
    "email",
    "instagram",
    "address",
    "city",
    "district",
    "province",
    "postcode",
    "opening_hours",
    "qualification",
    "notes",
)
_CLEAR_SUBMITTED_REVIEW_DRAFT_KEY = "lead_review_clear_submitted_draft"


@st.dialog("How to review a lead", width="large")
def _show_review_guide() -> None:
    st.markdown(
        """
        Review one business at a time and save the complete decision in one step.

        **1. Choose the queue order**

        Use **Sort by** to change the queue order, including the calculated
        **Transparent suggestion score** from highest to lowest. Use
        **Qualification filter** when you want to show only High, Medium, Low,
        Not Qualified, or Unknown leads. These preferences remain active while
        your browser session is open. Changing either control returns you to the
        first lead.

        **2. Verify the business**

        Check the OpenStreetMap source, then correct the editable business, contact,
        location, and operating details when public information is missing or outdated.
        **Open website in new tab** uses the current draft URL without saving it or
        requesting it from the OpenLeadKit server. Draft edits remain available when
        you visit another page and return during the same browser session.

        **3. Read the quality signals**

        Review duplicate candidates, any previously recorded website-check results,
        and the transparent suggestion score. These signals support your decision
        but never replace it.

        **4. Set the qualification**

        Select High, Medium, Low, Not Qualified, or Unknown. You do not need to save
        this field separately.

        **5. Add optional review notes**

        Record concise evidence or context for future reviewers. Notes are saved with
        the final decision.

        **6. Save the decision**

        Choose **Approve** when the record is suitable for the lead workflow, or
        **Reject** when it should not progress. Either action saves all edited fields,
        qualification, notes, and the status in one transaction.
        """
    )
    st.info(
        "Draft edits remain temporary until you choose Approve or Reject. They survive page "
        "navigation during this browser session but are not written to the database."
    )
    if st.button("Close guide", type="primary", width="stretch"):
        st.rerun()


def _reset_review_index() -> None:
    st.session_state.review_index = 0


def _review_widget_key(field: str, business_id: uuid.UUID) -> str:
    """Keep editable review fields isolated to the business currently on screen."""
    return f"lead_review_{field}_{business_id}"


def _clear_submitted_review_draft() -> None:
    """Remove session draft values only after their database transaction succeeds."""
    business_id = st.session_state.pop(_CLEAR_SUBMITTED_REVIEW_DRAFT_KEY, None)
    if not isinstance(business_id, uuid.UUID):
        return
    for field in _REVIEW_DRAFT_FIELDS:
        st.session_state.pop(_review_widget_key(field, business_id), None)


def render() -> None:
    _clear_submitted_review_draft()

    if setup_page(
        "Verification queue",
        "Lead Review",
        "Correct one business at a time, then save every edit with one review decision.",
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
        persist_state="session",
    )
    qualification_filter = filter_column.selectbox(
        "Qualification filter",
        [None, *list(QualificationStatus)],
        format_func=lambda option: "All qualifications" if option is None else option.value,
        key="lead_review_qualification_filter",
        on_change=_reset_review_index,
        persist_state="session",
    )
    st.caption(
        "Sort and qualification preferences stay active for this browser session. "
        "Changing either control returns you to the first lead."
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
            "Complete the review",
            "Correct the details, set qualification, add an optional note, then decide once.",
            "ONE STEP",
        )
        with st.container(border=True):
            st.subheader("Website")
            website_input, website_action = st.columns(
                [2, 1],
                vertical_alignment="bottom",
            )
            website_url = website_input.text_input(
                "Official website",
                value=business.website_url or "",
                max_chars=2_048,
                placeholder="https://example.com",
                key=_review_widget_key("website_url", business.id),
                persist_state="session",
            )
            draft_website_url = normalize_url(website_url)
            if draft_website_url is not None:
                website_action.link_button(
                    "Open website in new tab",
                    draft_website_url,
                    icon=":material/open_in_new:",
                    width="stretch",
                    on_click="ignore",
                )
            else:
                website_action.button(
                    "Open website in new tab",
                    icon=":material/open_in_new:",
                    width="stretch",
                    disabled=True,
                )
                if website_url.strip():
                    st.caption("Enter a valid HTTP or HTTPS website URL to open it.")

            with st.container(border=False):
                st.subheader("Editable business details")
                st.caption(
                    "Use public business information only. Source identity and coordinates "
                    "remain read-only."
                )
                business_name = st.text_input(
                    "Business name",
                    value=business.business_name,
                    max_chars=500,
                    key=_review_widget_key("business_name", business.id),
                    persist_state="session",
                )
                contact_left, contact_right = st.columns(2)
                phone = contact_left.text_input(
                    "Phone number",
                    value=business.phone or "",
                    max_chars=300,
                    placeholder="+62 812 3456 7890",
                    key=_review_widget_key("phone", business.id),
                    persist_state="session",
                )
                email = contact_right.text_input(
                    "Public business email",
                    value=business.email or "",
                    max_chars=320,
                    placeholder="hello@example.com",
                    key=_review_widget_key("email", business.id),
                    persist_state="session",
                )
                instagram = st.text_input(
                    "Instagram",
                    value=business.instagram or "",
                    max_chars=300,
                    placeholder="@business or https://instagram.com/business",
                    key=_review_widget_key("instagram", business.id),
                    persist_state="session",
                )

                st.divider()
                st.subheader("Location and operating details")
                address = st.text_area(
                    "Address",
                    value=business.address or "",
                    max_chars=2_000,
                    key=_review_widget_key("address", business.id),
                    persist_state="session",
                )
                location_left, location_right = st.columns(2)
                city = location_left.text_input(
                    "City",
                    value=business.city or "",
                    max_chars=500,
                    key=_review_widget_key("city", business.id),
                    persist_state="session",
                )
                district = location_right.text_input(
                    "District",
                    value=business.district or "",
                    max_chars=500,
                    key=_review_widget_key("district", business.id),
                    persist_state="session",
                )
                region_left, region_right = st.columns(2)
                province = region_left.text_input(
                    "Province",
                    value=business.province or "",
                    max_chars=500,
                    key=_review_widget_key("province", business.id),
                    persist_state="session",
                )
                postcode = region_right.text_input(
                    "Postcode",
                    value=business.postcode or "",
                    max_chars=32,
                    key=_review_widget_key("postcode", business.id),
                    persist_state="session",
                )
                opening_hours = st.text_input(
                    "Opening hours",
                    value=business.opening_hours or "",
                    max_chars=500,
                    placeholder="Mo-Su 08:00-22:00",
                    key=_review_widget_key("opening_hours", business.id),
                    persist_state="session",
                )

                st.divider()
                st.subheader("Qualification and notes")
                qualification = st.selectbox(
                    "Qualification level",
                    list(QualificationStatus),
                    format_func=lambda item: item.value,
                    index=list(QualificationStatus).index(business.qualification_status),
                    key=_review_widget_key("qualification", business.id),
                    persist_state="session",
                )
                notes = st.text_area(
                    "Review notes (optional)",
                    value=business.raw_notes or "",
                    max_chars=5_000,
                    placeholder="Add evidence or context for the decision.",
                    key=_review_widget_key("notes", business.id),
                    persist_state="session",
                )
                st.caption(
                    "Approve or Reject saves every editable field in one transaction. Opening "
                    "the website does not save the draft."
                )
                action_columns = st.columns(2)
                reject = action_columns[0].button(
                    "Reject",
                    icon=":material/close:",
                    width="stretch",
                    key=_review_widget_key("reject", business.id),
                )
                approve = action_columns[1].button(
                    "Approve",
                    icon=":material/check:",
                    type="primary",
                    width="stretch",
                    key=_review_widget_key("approve", business.id),
                )

            decision = (
                ReviewStatus.APPROVED if approve else ReviewStatus.REJECTED if reject else None
            )
            if decision is not None:
                try:
                    details = LeadReviewDetails(
                        business_name=business_name,
                        website_url=website_url,
                        phone=phone,
                        email=email,
                        instagram=instagram,
                        address=address,
                        city=city,
                        district=district,
                        province=province,
                        postcode=postcode,
                        opening_hours=opening_hours,
                        notes=notes,
                    )
                except ValidationError as exc:
                    st.error("The review was not saved. Correct the fields below and try again.")
                    st.code(safe_validation_error(exc))
                else:
                    repository.update_review(
                        business,
                        review_status=decision,
                        qualification_status=qualification,
                        details=details,
                    )
                    session.commit()
                    st.session_state[_CLEAR_SUBMITTED_REVIEW_DRAFT_KEY] = business.id
                    st.rerun()
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
            width="stretch",
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
            width="stretch",
        )
    if go_previous:
        st.session_state.review_index = index - 1
        st.rerun()
    if go_next:
        st.session_state.review_index = index + 1
        st.rerun()

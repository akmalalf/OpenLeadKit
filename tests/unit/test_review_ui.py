"""Focused tests for the lead-review widget state."""

from __future__ import annotations

import uuid
from inspect import getsource
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from openleadkit.models import Business, QualificationStatus, ReviewStatus
from openleadkit.repositories import LeadRepository
from openleadkit.services.review import LeadReviewDetails
from openleadkit.ui import review
from openleadkit.ui.review import _clear_submitted_review_draft, _review_widget_key


def test_editable_widget_keys_are_scoped_to_each_business() -> None:
    first_business_id = uuid.uuid4()
    second_business_id = uuid.uuid4()

    first_notes_key = _review_widget_key("notes", first_business_id)

    assert first_notes_key != _review_widget_key("notes", second_business_id)
    assert first_notes_key != _review_widget_key("qualification", first_business_id)
    assert str(first_business_id) in first_notes_key


def test_review_actions_do_not_buffer_drafts_in_a_form() -> None:
    source = getsource(review.render)

    assert '"Save notes"' not in source
    assert '"Save qualification"' not in source
    assert ".form_submit_button(" not in source
    assert "with st.form(" not in source
    assert 'key=_review_widget_key("reject", business.id)' in source
    assert 'key=_review_widget_key("approve", business.id)' in source


def test_review_drafts_persist_for_the_session_and_website_opens_in_the_browser() -> None:
    source = getsource(review.render)

    assert source.count('persist_state="session"') == 15
    assert 'persist_state="page"' not in source
    assert '"Open website in new tab"' in source
    assert ".link_button(" in source
    assert 'on_click="ignore"' in source
    assert "WebsiteChecker" not in source
    assert source.index("if decision is not None:") < source.index("repository.update_review(")


def test_submitted_review_draft_is_cleared_without_touching_other_leads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submitted_business_id = uuid.uuid4()
    other_business_id = uuid.uuid4()
    submitted_notes_key = _review_widget_key("notes", submitted_business_id)
    other_notes_key = _review_widget_key("notes", other_business_id)
    state = {
        review._CLEAR_SUBMITTED_REVIEW_DRAFT_KEY: submitted_business_id,
        submitted_notes_key: "Saved note",
        other_notes_key: "Unsaved note for another lead",
    }
    monkeypatch.setattr(review.st, "session_state", state)

    _clear_submitted_review_draft()

    assert review._CLEAR_SUBMITTED_REVIEW_DRAFT_KEY not in state
    assert submitted_notes_key not in state
    assert state[other_notes_key] == "Unsaved note for another lead"


def test_review_details_are_normalized_before_persistence() -> None:
    details = LeadReviewDetails(
        business_name="  Arunika   Coffee  ",
        website_url="arunika.example/?utm_source=review",
        phone=" +62 812 3456 7890 ",
        email=" hello@arunika.example ",
        instagram="https://instagram.com/arunika.coffee/?ref=profile",
        address=" Jalan  Asia   Afrika  ",
        city=" Bandung ",
        district=" Sumur Bandung ",
        province=" Jawa Barat ",
        postcode=" 40111 ",
        opening_hours=" Mo-Su 08:00-22:00 ",
        notes="\nVerified from the official website.\n",
    )

    assert details.business_name == "Arunika Coffee"
    assert details.website_url == "https://arunika.example/"
    assert details.phone == "+62 812 3456 7890"
    assert details.email == "hello@arunika.example"
    assert details.instagram == "arunika.coffee"
    assert details.address == "Jalan Asia Afrika"
    assert details.notes == "Verified from the official website."


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("website_url", "ftp://arunika.example"),
        ("phone", "call us"),
        ("email", "hello-at-arunika.example"),
        ("instagram", "not a valid username"),
    ],
)
def test_review_details_reject_invalid_public_contact_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        LeadReviewDetails(business_name="Arunika Coffee", **{field: value})


def test_review_decision_updates_all_fields_and_audit_events_together() -> None:
    business = Business(
        id=uuid.uuid4(),
        osm_type="node",
        osm_id=10,
        business_name="Old Coffee",
        normalized_name="old coffee",
        category_key="cafe",
        category_label="Cafe",
        city="Bandung",
        source_url="https://www.openstreetmap.org/node/10",
        latitude=-6.9,
        longitude=107.6,
        review_status=ReviewStatus.NEW,
        qualification_status=QualificationStatus.UNKNOWN,
    )
    session = Mock(spec=Session)
    details = LeadReviewDetails(
        business_name="Arunika Coffee",
        website_url="arunika.example",
        phone="+62 812 3456 7890",
        email="hello@arunika.example",
        instagram="@arunika.coffee",
        address="Jalan Asia Afrika",
        city="Bandung",
        district="Sumur Bandung",
        province="Jawa Barat",
        postcode="40111",
        opening_hours="Mo-Su 08:00-22:00",
        notes="Verified public contact details.",
    )

    repository = LeadRepository(session)
    duplicate_check = Mock(return_value=0)
    repository._create_duplicate_candidates = duplicate_check

    repository.update_review(
        business,
        review_status=ReviewStatus.APPROVED,
        qualification_status=QualificationStatus.HIGH,
        details=details,
    )

    assert business.business_name == "Arunika Coffee"
    assert business.normalized_name == "arunika coffee"
    assert business.website_url == "https://arunika.example/"
    assert business.normalized_domain == "arunika.example"
    assert business.phone == "+62 812 3456 7890"
    assert business.normalized_phone == "+6281234567890"
    assert business.email == "hello@arunika.example"
    assert business.instagram == "arunika.coffee"
    assert business.review_status == ReviewStatus.APPROVED
    assert business.qualification_status == QualificationStatus.HIGH
    assert business.raw_notes == "Verified public contact details."
    duplicate_check.assert_called_once_with(business)

    event_types = {call.args[0].event_type for call in session.add.call_args_list}
    assert {
        "Business Name",
        "Website",
        "Phone",
        "Email",
        "Instagram",
        "Address",
        "District",
        "Province",
        "Postcode",
        "Opening Hours",
        "Review Status",
        "Qualification",
        "Notes",
    } <= event_types

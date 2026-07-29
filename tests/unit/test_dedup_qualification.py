import uuid
from datetime import UTC, datetime

from openleadkit.models import Business, DuplicateMatchType
from openleadkit.schemas import BusinessRecord
from openleadkit.services.deduplication import (
    canonical_pair,
    exact_match,
    fuzzy_name_score,
    potential_name_match,
)
from openleadkit.services.qualification import (
    QualificationInputs,
    calculate_suggestion,
)
from openleadkit.ui.duplicates import _business_fields


def record(**updates: object) -> BusinessRecord:
    values = {
        "osm_type": "node",
        "osm_id": 10,
        "business_name": "Healthy Clinic",
        "normalized_name": "healthy clinic",
        "category_key": "clinic",
        "category_label": "Clinic",
        "city": "London",
        "source_url": "https://www.openstreetmap.org/node/10",
        "latitude": -6.9,
        "longitude": 107.6,
        "raw_element": {},
    }
    values.update(updates)
    return BusinessRecord.model_validate(values)


def business(**updates: object) -> Business:
    values = record().model_dump(exclude={"raw_element"})
    values.update(updates)
    return Business(**values)


def test_exact_match_order() -> None:
    candidate = business(normalized_domain="sehat.id", normalized_phone="+6221555")
    assert exact_match(record(), candidate).match_type == DuplicateMatchType.OSM_IDENTITY
    assert (
        exact_match(record(osm_id=11, normalized_domain="sehat.id"), candidate).match_type
        == DuplicateMatchType.DOMAIN
    )
    assert (
        exact_match(record(osm_id=11, normalized_phone="+6221555"), candidate).match_type
        == DuplicateMatchType.PHONE
    )


def test_fuzzy_threshold_and_same_city() -> None:
    candidate = business(osm_id=12, normalized_name="healthy clinic central")
    score = fuzzy_name_score("healthy clinic", "healthy clinic central")
    assert 0 < score < 1
    assert potential_name_match(record(), candidate, score - 0.01) is not None
    assert potential_name_match(record(), candidate, score + 0.01) is None
    candidate.city = "Manchester"
    assert potential_name_match(record(), candidate, 0.1) is None


def test_canonical_pair() -> None:
    left = uuid.UUID("00000000-0000-0000-0000-000000000002")
    right = uuid.UUID("00000000-0000-0000-0000-000000000001")
    assert canonical_pair(left, right) == (right, left)


def test_duplicate_comparison_fields_are_arrow_safe_strings() -> None:
    candidate = business(
        city=None,
        first_seen_at=datetime(2026, 7, 30, 1, 48, tzinfo=UTC),
    )

    fields = _business_fields(candidate)

    assert fields["City"] == "—"
    assert fields["First seen"] == "2026-07-30 01:48 UTC"
    assert all(isinstance(value, str) for value in fields.values())


def test_transparent_qualification_score() -> None:
    result = calculate_suggestion(
        QualificationInputs(
            has_website=False,
            website_available=False,
            has_phone=True,
            has_public_email=True,
            mobile_viewport_found=False,
            https_enabled=False,
            contact_page_found=True,
            complete_address=True,
            search_count=2,
        )
    )
    assert result.score == 100
    assert any("phone number" in reason for reason in result.explanation)

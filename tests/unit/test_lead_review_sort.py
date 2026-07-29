from unittest.mock import Mock

from sqlalchemy.dialects import postgresql

from openleadkit.models import QualificationStatus
from openleadkit.repositories import LeadReviewSort, LeadViewRepository


def _compiled_sort_query(
    sort_by: LeadReviewSort,
    qualification: QualificationStatus | None = None,
) -> str:
    session = Mock()
    session.scalars.return_value = []
    LeadViewRepository(session).business_ids(sort_by, qualification)
    statement = session.scalars.call_args.args[0]
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_needs_review_sort_prioritizes_status_then_discovery_time() -> None:
    query = _compiled_sort_query(LeadReviewSort.NEEDS_REVIEW)

    assert "CASE WHEN (businesses.review_status = 'New')" in query
    assert "businesses.first_seen_at DESC" in query
    assert query.endswith("businesses.id ASC")


def test_city_sort_places_empty_cities_last_and_uses_name_as_tie_breaker() -> None:
    query = _compiled_sort_query(LeadReviewSort.CITY_ASC)

    assert "businesses.city ASC NULLS LAST" in query
    assert "businesses.business_name ASC" in query
    assert query.endswith("businesses.id ASC")


def test_suggestion_score_sort_uses_the_transparent_signal_weights() -> None:
    query = _compiled_sort_query(LeadReviewSort.SUGGESTION_SCORE_DESC)

    assert "LEFT OUTER JOIN website_checks AS latest_website_check" in query
    assert "businesses.website_url IS NULL" in query
    assert "latest_website_check.http_status >= 400" in query
    assert "count(business_search_runs.search_run_id)" in query
    assert "THEN 20 ELSE 0 END" in query
    assert "businesses.first_seen_at DESC" in query


def test_qualification_filter_limits_the_database_query() -> None:
    query = _compiled_sort_query(
        LeadReviewSort.SUGGESTION_SCORE_DESC,
        QualificationStatus.HIGH,
    )

    assert "WHERE businesses.qualification_status = 'High'" in query

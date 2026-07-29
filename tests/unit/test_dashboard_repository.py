from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import postgresql

from openleadkit.repositories import LeadViewRepository


def test_dashboard_groups_status_counts_into_two_aggregate_queries() -> None:
    session = Mock()
    session.execute.side_effect = [
        Mock(one=Mock(return_value=(12, 5, 3, 2, 2, 4))),
        Mock(one=Mock(return_value=(7, 1))),
    ]
    session.scalars.return_value = []
    session.scalar.side_effect = [2, None]

    snapshot = LeadViewRepository(session).dashboard()

    assert (
        snapshot.total_businesses,
        snapshot.new,
        snapshot.reviewed,
        snapshot.approved,
        snapshot.exported,
        snapshot.high_priority,
    ) == (12, 5, 3, 2, 2, 4)
    assert (snapshot.completed_searches, snapshot.failed_searches) == (7, 1)
    assert snapshot.pending_duplicates == 2
    assert session.execute.call_count == 2

    business_query = str(
        session.execute.call_args_list[0].args[0].compile(dialect=postgresql.dialect())
    )
    search_query = str(
        session.execute.call_args_list[1].args[0].compile(dialect=postgresql.dialect())
    )
    assert business_query.count("FILTER (WHERE") == 5
    assert search_query.count("FILTER (WHERE") == 2


def test_recent_completed_searches_uses_five_item_default_limit() -> None:
    session = Mock()
    session.scalars.return_value = []

    assert LeadViewRepository(session).recent_completed_searches() == []

    statement = session.scalars.call_args.args[0]
    query = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "WHERE search_runs.status = 'Completed'" in query
    assert "search_runs.finished_at DESC NULLS LAST" in query
    assert "LIMIT 5" in query


def test_recent_completed_searches_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        LeadViewRepository(Mock()).recent_completed_searches(0)

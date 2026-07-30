import uuid
from inspect import getsource
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import postgresql

from openleadkit.models import ReviewStatus
from openleadkit.repositories import LeadViewRepository
from openleadkit.ui import history
from openleadkit.ui.history import _export_history_summary, _resolve_export_file


def test_export_history_page_uses_database_limit_and_offset() -> None:
    session = Mock()
    expected = [SimpleNamespace(id=uuid.uuid4())]
    session.scalars.return_value = expected

    result = LeadViewRepository(session).export_history_page(page=3, page_size=10)

    assert result == expected
    statement = session.scalars.call_args.args[0]
    query = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "ORDER BY export_logs.created_at DESC, export_logs.id DESC" in query
    assert "LIMIT 10 OFFSET 20" in query


def test_export_history_pagination_rejects_invalid_bounds() -> None:
    repository = LeadViewRepository(Mock())

    with pytest.raises(ValueError, match="page"):
        repository.export_history_page(page=0, page_size=10)
    with pytest.raises(ValueError, match="page size"):
        repository.export_history_page(page=1, page_size=101)


def test_exportable_history_page_filters_completed_nonempty_batches() -> None:
    session = Mock()
    session.scalars.return_value = []

    LeadViewRepository(session).exportable_history_page(page=2, page_size=25)

    statement = session.scalars.call_args.args[0]
    query = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "export_logs.status = 'Completed'" in query
    assert "export_logs.exported_count > 0" in query
    assert "LIMIT 25 OFFSET 25" in query


def test_combined_export_selection_deduplicates_and_reports_missing_records() -> None:
    approved_id = uuid.uuid4()
    historical_id = uuid.uuid4()
    missing_id = uuid.uuid4()
    approved = SimpleNamespace(id=approved_id, review_status=ReviewStatus.APPROVED)
    historical = SimpleNamespace(id=historical_id, review_status=ReviewStatus.EXPORTED)
    session = Mock()
    session.scalars.return_value = [approved, historical]
    export_log = SimpleNamespace(
        exported_business_ids=[str(historical_id), str(historical_id), str(missing_id)]
    )

    selection = LeadViewRepository(session).export_business_selection(
        [export_log],
        include_approved=True,
    )

    assert selection.businesses == (approved, historical)
    assert selection.approved_business_ids == frozenset({approved_id})
    assert selection.missing_historical_count == 1


def test_exported_business_page_preserves_logged_order_and_missing_ids() -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    first = SimpleNamespace(id=first_id)
    second = SimpleNamespace(id=second_id)
    session = Mock()
    session.scalars.return_value = [second, first]
    export_log = SimpleNamespace(
        exported_business_ids=[str(first_id), "invalid-id", str(second_id)]
    )

    entries, total = LeadViewRepository(session).exported_business_page(
        export_log,
        page=1,
        page_size=3,
    )

    assert total == 3
    assert [entry.business_id for entry in entries] == [
        str(first_id),
        "invalid-id",
        str(second_id),
    ]
    assert [entry.business for entry in entries] == [first, None, second]


def test_export_file_resolution_stays_inside_configured_directory(tmp_path: Path) -> None:
    export_directory = tmp_path / "exports"
    export_directory.mkdir()
    workbook = export_directory / "batch.xlsx"
    workbook.write_bytes(b"xlsx")
    outside = tmp_path / "outside.xlsx"
    outside.write_bytes(b"xlsx")

    assert (
        _resolve_export_file(
            "exports/batch.xlsx",
            project_root=tmp_path,
            export_directory=export_directory,
        )
        == workbook
    )
    assert (
        _resolve_export_file(
            str(outside),
            project_root=tmp_path,
            export_directory=export_directory,
        )
        is None
    )


def test_export_history_summary_never_exposes_the_workbook_path() -> None:
    output_path = "/srv/openleadkit/exports/private/batch.xlsx"
    export_log = SimpleNamespace(
        exported_at=None,
        created_at="2026-07-31",
        batch_id="BATCH-001",
        status=SimpleNamespace(value="Completed"),
        exported_count=10,
        skipped_existing_count=1,
        skipped_invalid_count=0,
        error_message=None,
        workbook_output=output_path,
    )

    summary = _export_history_summary([export_log])

    assert "Output" not in summary[0]
    assert "File" not in summary[0]
    assert output_path not in str(summary)
    assert summary[0]["Batch"] == "BATCH-001"


def test_history_tabs_execute_only_the_selected_view() -> None:
    source = getsource(history.render)

    assert 'on_change="rerun"' in source
    assert "if tabs[0].open:" in source
    assert "elif tabs[4].open:" in source


def test_export_details_offer_download_without_rendering_a_file_path() -> None:
    source = getsource(history._render_export_details)

    assert '"Download workbook"' in source
    assert 'st.caption(f"File:' not in source

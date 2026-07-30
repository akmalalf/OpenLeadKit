import uuid
from datetime import UTC, datetime
from inspect import getsource
from types import SimpleNamespace

from openleadkit.models import QualificationStatus
from openleadkit.ui import export
from openleadkit.ui.export import _build_export_records


def test_export_records_use_latest_preloaded_search_without_repository_queries() -> None:
    earlier = SimpleNamespace(
        category_label="Cafe",
        area_query="Old area",
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    latest = SimpleNamespace(
        category_label="Cafe",
        area_query="Current area",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    business = SimpleNamespace(
        id=uuid.uuid4(),
        business_name="Arunika Coffee",
        category_label="Cafe",
        city="Bandung",
        address="Jalan Asia Afrika",
        source_url="https://www.openstreetmap.org/node/1",
        website_url="https://arunika.example",
        phone="+622112345",
        email="hello@arunika.example",
        instagram="arunika",
        opening_hours="Mo-Su 08:00-22:00",
        latitude=-6.921,
        longitude=107.607,
        qualification_status=QualificationStatus.HIGH,
        raw_notes="Reviewed",
        search_runs=[
            SimpleNamespace(search_run=earlier),
            SimpleNamespace(search_run=latest),
        ],
    )

    records = _build_export_records((business,))

    assert len(records) == 1
    assert records[0].business_id == business.id
    assert records[0].search_query == "Cafe — Current area"


def test_crm_export_selector_supports_paginated_multi_batch_selection() -> None:
    source = getsource(export._render_export_source_selector)

    assert "exportable_history_page" in source
    assert "st.multiselect(" in source
    assert "SELECTED_BATCHES_KEY" in source
    assert "Add selected batches" in source
    assert 'vertical_alignment="bottom"' in source
    assert source.count('width="stretch"') >= 3

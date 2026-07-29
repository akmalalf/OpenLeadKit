from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from openleadkit.models import (
    Business,
    BusinessMerge,
    DuplicateCandidate,
    ExportLog,
    ExportStatus,
    QualificationStatus,
    ReviewEvent,
    ReviewStatus,
    SearchRun,
)
from openleadkit.repositories import LeadRepository
from openleadkit.schemas import BoundingBox, BusinessRecord
from openleadkit.services.area_lookup import AreaResult, cache_selected_area, cached_area

pytestmark = pytest.mark.integration


def search_run(session: Session) -> SearchRun:
    run = SearchRun(
        category_key="cafe",
        category_label="Cafe",
        area_query="London",
        south=-7,
        west=107.5,
        north=-6.8,
        east=107.8,
        maximum_results=100,
        generated_query="query",
        query_hash="a" * 64,
    )
    session.add(run)
    session.flush()
    return run


def record(osm_id: int, **changes: object) -> BusinessRecord:
    values = {
        "osm_type": "node",
        "osm_id": osm_id,
        "business_name": f"Arunika Coffee {osm_id}",
        "normalized_name": f"arunika coffee {osm_id}",
        "category_key": "cafe",
        "category_label": "Cafe",
        "city": "London",
        "source_url": f"https://www.openstreetmap.org/node/{osm_id}",
        "latitude": -6.91,
        "longitude": 107.61,
        "raw_element": {"id": osm_id},
    }
    values.update(changes)
    return BusinessRecord.model_validate(values)


def test_migration_extensions_and_business_upsert(integration_session: Session) -> None:
    session = integration_session
    assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0001_initial"
    extensions = set(
        session.scalars(
            text("SELECT extname FROM pg_extension WHERE extname IN ('citext', 'pg_trgm')")
        )
    )
    assert extensions == {"citext", "pg_trgm"}
    run = search_run(session)
    repository = LeadRepository(session)
    business, created, candidates = repository.upsert_osm_record(record(1), run.id)
    assert created and candidates == 0
    repeated, created_again, _ = repository.upsert_osm_record(
        record(1, phone="020 7946 0958", normalized_phone="02079460958"), run.id
    )
    session.flush()
    assert not created_again
    assert repeated.id == business.id
    assert repeated.phone == "020 7946 0958"
    assert len(repeated.search_runs) == 1
    assert session.scalar(select(Business).where(Business.osm_id == 1)) is not None
    selected_area = AreaResult(
        display_name="London, Greater London",
        bounding_box=BoundingBox(south=-7.0, west=107.5, north=-6.8, east=107.8),
        raw_response={"place_id": 17},
    )
    cache_selected_area(session, "London", selected_area)
    session.flush()
    cached = cached_area(session, "  LONDON ")
    assert cached is not None
    assert cached.display_name == "London, Greater London"


def test_duplicate_review_audit_merge_and_export_log(integration_session: Session) -> None:
    session = integration_session
    run = search_run(session)
    repository = LeadRepository(session, duplicate_threshold=0.7)
    left, _, _ = repository.upsert_osm_record(
        record(10, normalized_domain="arunika.id", website_url="https://arunika.id"), run.id
    )
    right, _, candidate_count = repository.upsert_osm_record(
        record(11, normalized_domain="arunika.id", phone="+6221555"), run.id
    )
    session.flush()
    assert candidate_count >= 1
    repository.update_review(
        left,
        review_status=ReviewStatus.APPROVED,
        qualification_status=QualificationStatus.HIGH,
        notes="Priority for this week",
    )
    session.flush()
    assert (
        session.scalar(
            select(ReviewEvent).where(
                ReviewEvent.business_id == left.id, ReviewEvent.event_type == "Review Status"
            )
        )
        is not None
    )
    audit = repository.merge(
        left, right, reason="Same domain, manually confirmed", merged_by="pytest"
    )
    session.flush()
    assert isinstance(audit, BusinessMerge)
    assert session.get(Business, right.id) is None
    assert audit.merged_snapshot["phone"] == "+6221555"
    assert left.phone == "+6221555"
    log = ExportLog(
        workbook_source="input/test.xlsx",
        workbook_output="exports/test.xlsx",
        batch_id=f"TEST-{uuid.uuid4()}",
        exported_count=1,
        status=ExportStatus.COMPLETED,
        exported_business_ids=[str(left.id)],
        exported_at=datetime.now(UTC),
    )
    session.add(log)
    session.flush()
    assert session.get(ExportLog, log.id).status == ExportStatus.COMPLETED


def test_exact_duplicate_without_location_is_persisted(integration_session: Session) -> None:
    session = integration_session
    run = search_run(session)
    repository = LeadRepository(session)
    left, _, _ = repository.upsert_osm_record(
        record(20, city=None, normalized_domain="no-location.example"),
        run.id,
    )
    right, _, candidate_count = repository.upsert_osm_record(
        record(21, city=None, normalized_domain="no-location.example"),
        run.id,
    )
    session.flush()
    candidate = session.scalar(
        select(DuplicateCandidate).where(
            DuplicateCandidate.business_id.in_((left.id, right.id)),
            DuplicateCandidate.candidate_business_id.in_((left.id, right.id)),
        )
    )
    assert candidate_count == 1
    assert candidate is not None

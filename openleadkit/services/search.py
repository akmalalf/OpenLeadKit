"""Atomic, database-locked business search workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from openleadkit.config import Settings
from openleadkit.models import SearchRun, SearchStatus
from openleadkit.repositories import LeadRepository
from openleadkit.schemas import BoundingBox, Category
from openleadkit.services.overpass import OverpassClient, build_overpass_query, query_hash


def advisory_lock_key(hash_value: str) -> int:
    unsigned = int(hash_value[:16], 16)
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


def recent_completed_search(
    session: Session, hash_value: str, *, hours: int = 24
) -> SearchRun | None:
    return session.scalar(
        select(SearchRun)
        .where(
            SearchRun.query_hash == hash_value,
            SearchRun.status == SearchStatus.COMPLETED,
            SearchRun.finished_at >= datetime.now(UTC) - timedelta(hours=hours),
        )
        .order_by(SearchRun.finished_at.desc())
    )


def run_search(
    session: Session,
    settings: Settings,
    category: Category,
    bbox: BoundingBox,
    *,
    area_query: str,
    area_display_name: str | None,
    maximum_results: int,
    require_phone: bool,
    require_website: bool,
    client: OverpassClient | None = None,
) -> SearchRun:
    query = build_overpass_query(
        category,
        bbox,
        maximum_results,
        require_phone=require_phone,
        require_website=require_website,
    )
    hash_value = query_hash(query)
    search_run = SearchRun(
        category_key=category.key,
        category_label=category.label,
        area_query=area_query[:300],
        area_display_name=area_display_name,
        south=bbox.south,
        west=bbox.west,
        north=bbox.north,
        east=bbox.east,
        maximum_results=maximum_results,
        generated_query=query,
        query_hash=hash_value,
        status=SearchStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(search_run)
    session.flush()
    locked = session.scalar(
        text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
        {"lock_key": advisory_lock_key(hash_value)},
    )
    if not locked:
        search_run.status = SearchStatus.CANCELLED
        search_run.error_type = "ConcurrentSearch"
        search_run.error_message = "An identical search is already running"
        search_run.finished_at = datetime.now(UTC)
        return search_run
    try:
        result = (client or OverpassClient(settings)).execute(query, category)
        repository = LeadRepository(session, settings.duplicate_name_threshold)
        for record in result.records[:maximum_results]:
            _, created, candidates = repository.upsert_osm_record(record, search_run.id)
            search_run.total_created += int(created)
            search_run.total_updated += int(not created)
            search_run.total_exact_duplicates += int(not created)
            search_run.total_possible_duplicates += candidates
        search_run.total_received = result.received
        search_run.raw_metadata = result.raw_metadata
        search_run.status = SearchStatus.COMPLETED
    except Exception as exc:
        search_run.status = SearchStatus.FAILED
        search_run.error_type = type(exc).__name__
        search_run.error_message = str(exc)[:2_000]
    finally:
        search_run.finished_at = datetime.now(UTC)
    return search_run

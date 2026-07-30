"""Transactional lead persistence, audit, deduplication, and merge operations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from openleadkit.models import (
    Business,
    BusinessMerge,
    BusinessSearchRun,
    DuplicateCandidate,
    DuplicateMatchType,
    DuplicateStatus,
    QualificationStatus,
    ReviewEvent,
    ReviewStatus,
    WebsiteCheck,
)
from openleadkit.schemas import BusinessRecord
from openleadkit.services.deduplication import canonical_pair
from openleadkit.services.normalization import (
    extract_domain,
    normalize_business_name,
    normalize_phone,
)
from openleadkit.services.review import LeadReviewDetails

REVIEW_DETAIL_FIELDS = (
    ("business_name", "Business Name"),
    ("website_url", "Website"),
    ("phone", "Phone"),
    ("email", "Email"),
    ("instagram", "Instagram"),
    ("address", "Address"),
    ("city", "City"),
    ("district", "District"),
    ("province", "Province"),
    ("postcode", "Postcode"),
    ("opening_hours", "Opening Hours"),
)
DUPLICATE_RELEVANT_REVIEW_FIELDS = {
    "business_name",
    "website_url",
    "phone",
    "city",
    "district",
}


class LeadRepository:
    """Repository methods expect the caller to own the transaction."""

    def __init__(self, session: Session, duplicate_threshold: float = 0.72) -> None:
        self.session = session
        self.duplicate_threshold = duplicate_threshold

    def upsert_osm_record(
        self, record: BusinessRecord, search_run_id: uuid.UUID
    ) -> tuple[Business, bool, int]:
        now = datetime.now(UTC)
        existing = self.session.scalar(
            select(Business).where(
                Business.osm_type == record.osm_type, Business.osm_id == record.osm_id
            )
        )
        created = existing is None
        if existing is None:
            values = record.model_dump(exclude={"raw_element"})
            existing = Business(**values)
            self.session.add(existing)
            self.session.flush()
        else:
            existing.last_seen_at = now
            for field, value in record.model_dump(exclude={"raw_element"}).items():
                if field in {"osm_type", "osm_id", "first_seen_at"}:
                    continue
                if value not in (None, "") and getattr(existing, field, None) in (None, ""):
                    setattr(existing, field, value)
        association = self.session.get(
            BusinessSearchRun,
            {"business_id": existing.id, "search_run_id": search_run_id},
        )
        if association:
            association.last_observed_at = now
            association.raw_element = record.raw_element
        else:
            self.session.add(
                BusinessSearchRun(
                    business_id=existing.id,
                    search_run_id=search_run_id,
                    raw_element=record.raw_element,
                )
            )
        candidates = 0 if not created else self._create_duplicate_candidates(existing)
        return existing, created, candidates

    def _create_duplicate_candidates(self, business: Business) -> int:
        exact_filters = []
        if business.normalized_domain:
            exact_filters.append(Business.normalized_domain == business.normalized_domain)
        if business.normalized_phone:
            exact_filters.append(Business.normalized_phone == business.normalized_phone)
        exact_matches = (
            list(
                self.session.scalars(
                    select(Business).where(Business.id != business.id, or_(*exact_filters))
                )
            )
            if exact_filters
            else []
        )
        matches: dict[uuid.UUID, tuple[DuplicateMatchType, float]] = {}
        for candidate in exact_matches:
            if (
                business.normalized_domain
                and candidate.normalized_domain == business.normalized_domain
            ):
                matches[candidate.id] = (DuplicateMatchType.DOMAIN, 1.0)
            elif (
                business.normalized_phone
                and candidate.normalized_phone == business.normalized_phone
            ):
                matches[candidate.id] = (DuplicateMatchType.PHONE, 1.0)

        area_filters = []
        if business.city:
            area_filters.append(Business.city == business.city)
        if business.district:
            area_filters.append(Business.district == business.district)
        if area_filters:
            area_filter = or_(*area_filters)
            fuzzy_rows = self.session.execute(
                select(
                    Business,
                    func.similarity(Business.normalized_name, business.normalized_name).label(
                        "score"
                    ),
                ).where(
                    Business.id != business.id,
                    area_filter,
                    func.similarity(Business.normalized_name, business.normalized_name)
                    >= self.duplicate_threshold,
                )
            )
            for candidate, score in fuzzy_rows:
                matches.setdefault(candidate.id, (DuplicateMatchType.NAME_CITY, float(score)))

        for candidate_id, (match_type, score) in matches.items():
            left, right = canonical_pair(business.id, candidate_id)
            statement = (
                insert(DuplicateCandidate)
                .values(
                    business_id=left,
                    candidate_business_id=right,
                    match_type=match_type,
                    similarity_score=score,
                )
                .on_conflict_do_nothing(constraint="uq_duplicate_candidate_pair")
            )
            self.session.execute(statement)
        return len(matches)

    def update_review(
        self,
        business: Business,
        *,
        review_status: ReviewStatus | None = None,
        qualification_status: QualificationStatus | None = None,
        notes: str | None = None,
        details: LeadReviewDetails | None = None,
    ) -> None:
        changes: list[tuple[str, str | None, str | None]] = []
        duplicate_fields_changed = False
        if details is not None:
            for field, event_type in REVIEW_DETAIL_FIELDS:
                previous = getattr(business, field)
                new = getattr(details, field)
                if previous != new:
                    changes.append((event_type, previous, new))
                    setattr(business, field, new)
                    duplicate_fields_changed = (
                        duplicate_fields_changed or field in DUPLICATE_RELEVANT_REVIEW_FIELDS
                    )
            business.normalized_name = normalize_business_name(details.business_name)
            business.normalized_domain = extract_domain(details.website_url)
            business.normalized_phone = normalize_phone(details.phone)
            if duplicate_fields_changed:
                self._create_duplicate_candidates(business)

        if review_status is not None and business.review_status != review_status:
            changes.append(("Review Status", business.review_status.value, review_status.value))
            business.review_status = review_status
        if (
            qualification_status is not None
            and business.qualification_status != qualification_status
        ):
            changes.append(
                (
                    "Qualification",
                    business.qualification_status.value,
                    qualification_status.value,
                )
            )
            business.qualification_status = qualification_status
        submitted_notes = details.notes if details is not None else notes
        if (details is not None or notes is not None) and business.raw_notes != submitted_notes:
            changes.append(("Notes", business.raw_notes, submitted_notes))
            business.raw_notes = submitted_notes
        for event_type, previous, new in changes:
            self.session.add(
                ReviewEvent(
                    business_id=business.id,
                    event_type=event_type,
                    previous_value=previous,
                    new_value=new,
                )
            )

    def decide_duplicate(
        self, candidate: DuplicateCandidate, status: DuplicateStatus, notes: str | None = None
    ) -> None:
        candidate.status = status
        candidate.decision_notes = notes
        candidate.resolved_at = datetime.now(UTC)
        for business_id in (candidate.business_id, candidate.candidate_business_id):
            self.session.add(
                ReviewEvent(
                    business_id=business_id,
                    event_type="Duplicate Decision",
                    previous_value=DuplicateStatus.PENDING.value,
                    new_value=status.value,
                    notes=notes,
                )
            )

    def merge(
        self,
        survivor: Business,
        merged: Business,
        *,
        reason: str,
        merged_by: str,
    ) -> BusinessMerge:
        if survivor.id == merged.id:
            raise ValueError("A business cannot be merged with itself")
        snapshot = {
            column.name: _json_value(getattr(merged, column.name))
            for column in Business.__table__.columns
        }
        for column in Business.__table__.columns:
            name = column.name
            if name in {"id", "osm_type", "osm_id", "created_at", "updated_at"}:
                continue
            survivor_value = getattr(survivor, name)
            merged_value = getattr(merged, name)
            if survivor_value in (None, "") and merged_value not in (None, ""):
                setattr(survivor, name, merged_value)

        association_insert = insert(BusinessSearchRun).from_select(
            [
                "business_id",
                "search_run_id",
                "first_observed_at",
                "last_observed_at",
                "raw_element",
            ],
            select(
                literal(survivor.id),
                BusinessSearchRun.search_run_id,
                BusinessSearchRun.first_observed_at,
                BusinessSearchRun.last_observed_at,
                BusinessSearchRun.raw_element,
            ).where(BusinessSearchRun.business_id == merged.id),
        )
        self.session.execute(
            association_insert.on_conflict_do_update(
                index_elements=[
                    BusinessSearchRun.business_id,
                    BusinessSearchRun.search_run_id,
                ],
                set_={
                    "first_observed_at": func.least(
                        BusinessSearchRun.first_observed_at,
                        association_insert.excluded.first_observed_at,
                    ),
                    "last_observed_at": func.greatest(
                        BusinessSearchRun.last_observed_at,
                        association_insert.excluded.last_observed_at,
                    ),
                    "raw_element": association_insert.excluded.raw_element,
                },
            )
        )
        self.session.execute(
            delete(BusinessSearchRun).where(BusinessSearchRun.business_id == merged.id)
        )
        self.session.execute(
            update(WebsiteCheck)
            .where(WebsiteCheck.business_id == merged.id)
            .values(business_id=survivor.id)
        )
        self.session.execute(
            update(ReviewEvent)
            .where(ReviewEvent.business_id == merged.id)
            .values(business_id=survivor.id)
        )
        self.session.execute(
            delete(DuplicateCandidate).where(
                or_(
                    DuplicateCandidate.business_id == merged.id,
                    DuplicateCandidate.candidate_business_id == merged.id,
                )
            )
        )
        audit = BusinessMerge(
            surviving_business_id=survivor.id,
            merged_business_id=merged.id,
            merged_snapshot=snapshot,
            reason=reason,
            merged_by=merged_by,
        )
        self.session.add(audit)
        self.session.add(
            ReviewEvent(
                business_id=survivor.id,
                event_type="Merge",
                previous_value=str(merged.id),
                new_value=str(survivor.id),
                notes=reason,
            )
        )
        self.session.delete(merged)
        self.session.flush()
        return audit


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, uuid.UUID)):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value

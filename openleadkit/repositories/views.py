"""Read-oriented queries used by Streamlit coordinators."""

from __future__ import annotations

import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from openleadkit.models import (
    Business,
    BusinessSearchRun,
    DuplicateCandidate,
    DuplicateStatus,
    ExportLog,
    ExportStatus,
    QualificationStatus,
    ReviewEvent,
    ReviewStatus,
    SearchRun,
    SearchStatus,
    WebsiteCheck,
)


@dataclass(frozen=True)
class DashboardSnapshot:
    total_businesses: int
    new: int
    reviewed: int
    approved: int
    exported: int
    high_priority: int
    pending_duplicates: int
    completed_searches: int
    failed_searches: int
    recent_searches: tuple[SearchRun, ...]
    last_search: SearchRun | None
    last_export: ExportLog | None


@dataclass(frozen=True)
class ExportedBusinessEntry:
    business_id: str
    business: Business | None


@dataclass(frozen=True)
class ExportBusinessSelection:
    businesses: tuple[Business, ...]
    approved_business_ids: frozenset[uuid.UUID]
    missing_historical_count: int


class LeadReviewSort(enum.StrEnum):
    NEEDS_REVIEW = "Needs review first"
    NEWEST = "Newest discovered"
    OLDEST = "Oldest discovered"
    NAME_ASC = "Business name A-Z"
    NAME_DESC = "Business name Z-A"
    CITY_ASC = "City A-Z"
    SUGGESTION_SCORE_DESC = "Transparent suggestion score"


class LeadViewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _count(self, model: type[Any], *filters: ColumnElement[bool]) -> int:
        result = self.session.scalar(select(func.count()).select_from(model).where(*filters))
        return result or 0

    def dashboard(self) -> DashboardSnapshot:
        (
            total_businesses,
            new,
            reviewed,
            approved,
            exported,
            high_priority,
        ) = self.session.execute(
            select(
                func.count(Business.id),
                func.count(Business.id).filter(Business.review_status == ReviewStatus.NEW),
                func.count(Business.id).filter(Business.review_status == ReviewStatus.REVIEWED),
                func.count(Business.id).filter(Business.review_status == ReviewStatus.APPROVED),
                func.count(Business.id).filter(Business.review_status == ReviewStatus.EXPORTED),
                func.count(Business.id).filter(
                    Business.qualification_status == QualificationStatus.HIGH
                ),
            )
        ).one()
        completed_searches, failed_searches = self.session.execute(
            select(
                func.count(SearchRun.id).filter(SearchRun.status == SearchStatus.COMPLETED),
                func.count(SearchRun.id).filter(SearchRun.status == SearchStatus.FAILED),
            )
        ).one()
        recent_searches = tuple(self.recent_completed_searches())
        return DashboardSnapshot(
            total_businesses=total_businesses,
            new=new,
            reviewed=reviewed,
            approved=approved,
            exported=exported,
            high_priority=high_priority,
            pending_duplicates=self._count(
                DuplicateCandidate, DuplicateCandidate.status == DuplicateStatus.PENDING
            ),
            completed_searches=completed_searches,
            failed_searches=failed_searches,
            recent_searches=recent_searches,
            last_search=recent_searches[0] if recent_searches else None,
            last_export=self.session.scalar(
                select(ExportLog)
                .where(ExportLog.status == ExportStatus.COMPLETED)
                .order_by(ExportLog.exported_at.desc())
                .limit(1)
            ),
        )

    def recent_completed_searches(self, limit: int = 5) -> list[SearchRun]:
        if limit < 1:
            raise ValueError("The recent search limit must be at least 1")
        return list(
            self.session.scalars(
                select(SearchRun)
                .where(SearchRun.status == SearchStatus.COMPLETED)
                .order_by(SearchRun.finished_at.desc().nulls_last(), SearchRun.id.asc())
                .limit(limit)
            )
        )

    def all_businesses(self) -> list[Business]:
        return list(
            self.session.scalars(
                select(Business)
                .options(
                    selectinload(Business.search_runs).selectinload(BusinessSearchRun.search_run)
                )
                .order_by(Business.last_seen_at.desc())
            )
        )

    def business_ids(
        self,
        sort_by: LeadReviewSort = LeadReviewSort.NEEDS_REVIEW,
        qualification: QualificationStatus | None = None,
    ) -> list[uuid.UUID]:
        review_priority = case(
            (Business.review_status == ReviewStatus.NEW, 0),
            (Business.review_status == ReviewStatus.REVIEWED, 1),
            (Business.review_status == ReviewStatus.APPROVED, 2),
            (Business.review_status == ReviewStatus.REJECTED, 3),
            (Business.review_status == ReviewStatus.EXPORTED, 4),
            else_=5,
        )
        statement = select(Business.id)
        order_by: tuple[ColumnElement[Any], ...]
        if sort_by == LeadReviewSort.SUGGESTION_SCORE_DESC:
            latest_check = aliased(WebsiteCheck, name="latest_website_check")
            check_lookup = aliased(WebsiteCheck, name="website_check_lookup")
            latest_check_id = (
                select(check_lookup.id)
                .where(check_lookup.business_id == Business.id)
                .order_by(check_lookup.created_at.desc(), check_lookup.id.desc())
                .limit(1)
                .correlate(Business)
                .scalar_subquery()
            )
            search_count = (
                select(func.count(BusinessSearchRun.search_run_id))
                .where(BusinessSearchRun.business_id == Business.id)
                .correlate(Business)
                .scalar_subquery()
            )

            def present(column: Any) -> ColumnElement[bool]:
                return and_(column.is_not(None), column != "")

            suggestion_score = (
                case((or_(Business.website_url.is_(None), Business.website_url == ""), 20), else_=0)
                + case((latest_check.http_status >= 400, 15), else_=0)
                + case((present(Business.phone), 15), else_=0)
                + case(
                    (
                        or_(
                            present(Business.email),
                            present(latest_check.public_email),
                        ),
                        15,
                    ),
                    else_=0,
                )
                + case((latest_check.mobile_viewport_found.is_(False), 10), else_=0)
                + case((latest_check.https_enabled.is_(False), 10), else_=0)
                + case((present(latest_check.contact_page_url), 5), else_=0)
                + case(
                    (
                        and_(
                            present(Business.address),
                            present(Business.city),
                        ),
                        5,
                    ),
                    else_=0,
                )
                + case((search_count > 1, 5), else_=0)
            )
            statement = statement.outerjoin(latest_check, latest_check.id == latest_check_id)
            order_by = (
                suggestion_score.desc(),
                Business.first_seen_at.desc(),
            )
        else:
            order_by = {
                LeadReviewSort.NEEDS_REVIEW: (
                    review_priority.asc(),
                    Business.first_seen_at.desc(),
                ),
                LeadReviewSort.NEWEST: (Business.first_seen_at.desc(),),
                LeadReviewSort.OLDEST: (Business.first_seen_at.asc(),),
                LeadReviewSort.NAME_ASC: (Business.business_name.asc(),),
                LeadReviewSort.NAME_DESC: (Business.business_name.desc(),),
                LeadReviewSort.CITY_ASC: (
                    Business.city.asc().nulls_last(),
                    Business.business_name.asc(),
                ),
            }[sort_by]
        if qualification is not None:
            statement = statement.where(Business.qualification_status == qualification)
        statement = statement.order_by(*order_by, Business.id.asc())
        return list(self.session.scalars(statement))

    def business(self, business_id: uuid.UUID) -> Business | None:
        return self.session.get(Business, business_id)

    def duplicates_for_business(self, business_id: uuid.UUID) -> list[DuplicateCandidate]:
        return list(
            self.session.scalars(
                select(DuplicateCandidate).where(
                    or_(
                        DuplicateCandidate.business_id == business_id,
                        DuplicateCandidate.candidate_business_id == business_id,
                    )
                )
            )
        )

    def latest_website_check(self, business_id: uuid.UUID) -> WebsiteCheck | None:
        return self.session.scalar(
            select(WebsiteCheck)
            .where(WebsiteCheck.business_id == business_id)
            .order_by(WebsiteCheck.created_at.desc())
            .limit(1)
        )

    def review_events(self, business_id: uuid.UUID) -> list[ReviewEvent]:
        return list(
            self.session.scalars(
                select(ReviewEvent)
                .where(ReviewEvent.business_id == business_id)
                .order_by(ReviewEvent.created_at.desc())
            )
        )

    def pending_duplicate_candidates(self) -> list[DuplicateCandidate]:
        return list(
            self.session.scalars(
                select(DuplicateCandidate)
                .where(DuplicateCandidate.status == DuplicateStatus.PENDING)
                .order_by(DuplicateCandidate.created_at)
            )
        )

    def approved_businesses(self) -> list[Business]:
        return list(
            self.session.scalars(
                select(Business)
                .where(Business.review_status == ReviewStatus.APPROVED)
                .order_by(Business.business_name)
            )
        )

    def latest_search_for_business(self, business_id: uuid.UUID) -> SearchRun | None:
        return self.session.scalar(
            select(SearchRun)
            .where(SearchRun.businesses.any(business_id=business_id))
            .order_by(SearchRun.created_at.desc())
            .limit(1)
        )

    def search_history(self) -> list[SearchRun]:
        return list(self.session.scalars(select(SearchRun).order_by(SearchRun.created_at.desc())))

    def website_history(self) -> list[WebsiteCheck]:
        return list(
            self.session.scalars(select(WebsiteCheck).order_by(WebsiteCheck.created_at.desc()))
        )

    def all_review_events(self) -> list[ReviewEvent]:
        return list(
            self.session.scalars(select(ReviewEvent).order_by(ReviewEvent.created_at.desc()))
        )

    def duplicate_history(self) -> list[DuplicateCandidate]:
        return list(
            self.session.scalars(
                select(DuplicateCandidate).order_by(DuplicateCandidate.created_at.desc())
            )
        )

    def export_history_count(self) -> int:
        return self._count(ExportLog)

    def export_history_page(self, page: int, page_size: int) -> list[ExportLog]:
        if page < 1:
            raise ValueError("The export history page must be at least 1")
        if not 1 <= page_size <= 100:
            raise ValueError("The export history page size must be between 1 and 100")
        return list(
            self.session.scalars(
                select(ExportLog)
                .order_by(ExportLog.created_at.desc(), ExportLog.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )

    def exportable_history_count(self) -> int:
        return self._count(
            ExportLog,
            ExportLog.status == ExportStatus.COMPLETED,
            ExportLog.exported_count > 0,
        )

    def exportable_history_page(self, page: int, page_size: int) -> list[ExportLog]:
        if page < 1:
            raise ValueError("The export selection page must be at least 1")
        if not 1 <= page_size <= 100:
            raise ValueError("The export selection page size must be between 1 and 100")
        return list(
            self.session.scalars(
                select(ExportLog)
                .where(
                    ExportLog.status == ExportStatus.COMPLETED,
                    ExportLog.exported_count > 0,
                )
                .order_by(ExportLog.created_at.desc(), ExportLog.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )

    def export_logs_by_ids(self, export_log_ids: Sequence[uuid.UUID]) -> list[ExportLog]:
        if not export_log_ids:
            return []
        return list(
            self.session.scalars(
                select(ExportLog)
                .where(
                    ExportLog.id.in_(export_log_ids),
                    ExportLog.status == ExportStatus.COMPLETED,
                    ExportLog.exported_count > 0,
                )
                .order_by(ExportLog.created_at.desc(), ExportLog.id.desc())
            )
        )

    def export_business_selection(
        self,
        export_logs: Sequence[ExportLog],
        *,
        include_approved: bool,
    ) -> ExportBusinessSelection:
        historical_ids: set[uuid.UUID] = set()
        for export_log in export_logs:
            for raw_id in export_log.exported_business_ids:
                try:
                    historical_ids.add(uuid.UUID(raw_id))
                except (TypeError, ValueError, AttributeError):
                    continue

        filters: list[ColumnElement[bool]] = []
        if include_approved:
            filters.append(Business.review_status == ReviewStatus.APPROVED)
        if historical_ids:
            filters.append(Business.id.in_(historical_ids))
        if not filters:
            return ExportBusinessSelection((), frozenset(), len(historical_ids))

        businesses = tuple(
            self.session.scalars(
                select(Business)
                .options(
                    selectinload(Business.search_runs).selectinload(BusinessSearchRun.search_run)
                )
                .where(or_(*filters))
                .order_by(Business.business_name.asc(), Business.id.asc())
            )
        )
        available_historical_ids = {
            business.id for business in businesses if business.id in historical_ids
        }
        approved_ids = frozenset(
            business.id
            for business in businesses
            if include_approved and business.review_status == ReviewStatus.APPROVED
        )
        return ExportBusinessSelection(
            businesses=businesses,
            approved_business_ids=approved_ids,
            missing_historical_count=len(historical_ids - available_historical_ids),
        )

    def exported_business_page(
        self,
        export_log: ExportLog,
        page: int,
        page_size: int,
    ) -> tuple[list[ExportedBusinessEntry], int]:
        if page < 1:
            raise ValueError("The exported-business page must be at least 1")
        if not 1 <= page_size <= 100:
            raise ValueError("The exported-business page size must be between 1 and 100")
        business_ids = export_log.exported_business_ids
        start = (page - 1) * page_size
        selected_ids = business_ids[start : start + page_size]
        parsed_ids: list[tuple[str, uuid.UUID | None]] = []
        for raw_id in selected_ids:
            try:
                parsed_ids.append((raw_id, uuid.UUID(raw_id)))
            except (TypeError, ValueError, AttributeError):
                parsed_ids.append((str(raw_id), None))
        valid_ids = [business_id for _, business_id in parsed_ids if business_id is not None]
        businesses = (
            list(self.session.scalars(select(Business).where(Business.id.in_(valid_ids))))
            if valid_ids
            else []
        )
        by_id = {business.id: business for business in businesses}
        return (
            [
                ExportedBusinessEntry(
                    business_id=raw_id,
                    business=by_id.get(business_id) if business_id is not None else None,
                )
                for raw_id, business_id in parsed_ids
            ],
            len(business_ids),
        )

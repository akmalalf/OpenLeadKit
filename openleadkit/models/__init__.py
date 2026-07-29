"""SQLAlchemy models for the complete OpenLeadKit schema."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class SearchStatus(enum.StrEnum):
    PENDING = "Pending"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


class ReviewStatus(enum.StrEnum):
    NEW = "New"
    REVIEWED = "Reviewed"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    EXPORTED = "Exported"


class QualificationStatus(enum.StrEnum):
    UNKNOWN = "Unknown"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    NOT_QUALIFIED = "Not Qualified"


class WebsiteCheckStatus(enum.StrEnum):
    PENDING = "Pending"
    COMPLETED = "Completed"
    BLOCKED = "Blocked"
    FAILED = "Failed"


class DuplicateMatchType(enum.StrEnum):
    OSM_IDENTITY = "OSM Identity"
    DOMAIN = "Domain"
    PHONE = "Phone"
    NAME_CITY = "Name and City"


class DuplicateStatus(enum.StrEnum):
    PENDING = "Pending"
    KEEP_BOTH = "Keep Both"
    MERGE = "Merge"
    IGNORE = "Ignore Candidate"
    RESOLVED = "Resolved"


class ExportStatus(enum.StrEnum):
    PENDING = "Pending"
    COMPLETED = "Completed"
    FAILED = "Failed"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )


class SearchRun(TimestampMixin, Base):
    __tablename__ = "search_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_key: Mapped[str] = mapped_column(String(80), nullable=False)
    category_label: Mapped[str] = mapped_column(String(160), nullable=False)
    area_query: Mapped[str] = mapped_column(String(300), nullable=False)
    area_display_name: Mapped[str | None] = mapped_column(String(500))
    south: Mapped[float] = mapped_column(Float, nullable=False)
    west: Mapped[float] = mapped_column(Float, nullable=False)
    north: Mapped[float] = mapped_column(Float, nullable=False)
    east: Mapped[float] = mapped_column(Float, nullable=False)
    maximum_results: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_query: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[SearchStatus] = mapped_column(
        Enum(
            SearchStatus, name="search_status", values_callable=lambda obj: [e.value for e in obj]
        ),
        default=SearchStatus.PENDING,
        nullable=False,
    )
    total_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_exact_duplicates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_possible_duplicates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_type: Mapped[str | None] = mapped_column(String(160))
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    businesses: Mapped[list[BusinessSearchRun]] = relationship(
        back_populates="search_run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_search_runs_query_hash", "query_hash"),
        Index("ix_search_runs_status", "status"),
        Index("ix_search_runs_created_at", "created_at"),
        CheckConstraint("south < north AND west < east", name="ck_search_runs_bbox_order"),
    )


class Business(TimestampMixin, Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    osm_type: Mapped[str] = mapped_column(String(16), nullable=False)
    osm_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    business_name: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    normalized_name: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    category_key: Mapped[str] = mapped_column(String(80), nullable=False)
    category_label: Mapped[str] = mapped_column(String(160), nullable=False)
    city: Mapped[str | None] = mapped_column(CITEXT())
    district: Mapped[str | None] = mapped_column(CITEXT())
    province: Mapped[str | None] = mapped_column(CITEXT())
    postcode: Mapped[str | None] = mapped_column(String(32))
    country_code: Mapped[str | None] = mapped_column(String(2))
    address: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    website_url: Mapped[str | None] = mapped_column(Text)
    normalized_domain: Mapped[str | None] = mapped_column(CITEXT())
    phone: Mapped[str | None] = mapped_column(String(300))
    normalized_phone: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(CITEXT())
    instagram: Mapped[str | None] = mapped_column(String(300))
    opening_hours: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(80), default="OpenStreetMap", nullable=False)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(
            ReviewStatus, name="review_status", values_callable=lambda obj: [e.value for e in obj]
        ),
        default=ReviewStatus.NEW,
        nullable=False,
    )
    qualification_status: Mapped[QualificationStatus] = mapped_column(
        Enum(
            QualificationStatus,
            name="qualification_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=QualificationStatus.UNKNOWN,
        nullable=False,
    )
    raw_notes: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    search_runs: Mapped[list[BusinessSearchRun]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    website_checks: Mapped[list[WebsiteCheck]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    review_events: Mapped[list[ReviewEvent]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("osm_type", "osm_id", name="uq_business_osm_identity"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_business_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_business_longitude"),
        Index("ix_business_normalized_name", "normalized_name"),
        Index("ix_business_normalized_phone", "normalized_phone"),
        Index("ix_business_normalized_domain", "normalized_domain"),
        Index("ix_business_city", "city"),
        Index("ix_business_category_key", "category_key"),
        Index("ix_business_review_status", "review_status"),
        Index("ix_business_qualification_status", "qualification_status"),
        Index("ix_business_first_seen_at", "first_seen_at"),
        Index("ix_business_last_seen_at", "last_seen_at"),
        Index(
            "ix_business_normalized_name_trgm",
            "normalized_name",
            postgresql_using="gin",
            postgresql_ops={"normalized_name": "gin_trgm_ops"},
        ),
    )


class BusinessSearchRun(Base):
    __tablename__ = "business_search_runs"

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True
    )
    search_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("search_runs.id", ondelete="CASCADE"), primary_key=True
    )
    first_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    raw_element: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    business: Mapped[Business] = relationship(back_populates="search_runs")
    search_run: Mapped[SearchRun] = relationship(back_populates="businesses")


class WebsiteCheck(Base):
    __tablename__ = "website_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    requested_url: Mapped[str] = mapped_column(Text, nullable=False)
    checked_url: Mapped[str | None] = mapped_column(Text)
    final_url: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(160))
    response_bytes: Mapped[int | None] = mapped_column(Integer)
    page_title: Mapped[str | None] = mapped_column(String(500))
    https_enabled: Mapped[bool | None]
    mobile_viewport_found: Mapped[bool | None]
    contact_page_url: Mapped[str | None] = mapped_column(Text)
    about_page_url: Mapped[str | None] = mapped_column(Text)
    public_email: Mapped[str | None] = mapped_column(CITEXT())
    public_phone: Mapped[str | None] = mapped_column(String(300))
    whatsapp_url: Mapped[str | None] = mapped_column(Text)
    instagram_url: Mapped[str | None] = mapped_column(Text)
    robots_allowed: Mapped[bool | None]
    status: Mapped[WebsiteCheckStatus] = mapped_column(
        Enum(
            WebsiteCheckStatus,
            name="website_check_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=WebsiteCheckStatus.PENDING,
        nullable=False,
    )
    error_type: Mapped[str | None] = mapped_column(String(160))
    error_message: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    business: Mapped[Business] = relationship(back_populates="website_checks")
    __table_args__ = (Index("ix_website_checks_business_checked", "business_id", "checked_at"),)


class DuplicateCandidate(TimestampMixin, Base):
    __tablename__ = "duplicate_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    candidate_business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    match_type: Mapped[DuplicateMatchType] = mapped_column(
        Enum(
            DuplicateMatchType,
            name="duplicate_match_type",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    similarity_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[DuplicateStatus] = mapped_column(
        Enum(
            DuplicateStatus,
            name="duplicate_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=DuplicateStatus.PENDING,
        nullable=False,
    )
    decision_notes: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("business_id < candidate_business_id", name="ck_duplicate_canonical_pair"),
        UniqueConstraint(
            "business_id", "candidate_business_id", name="uq_duplicate_candidate_pair"
        ),
        Index("ix_duplicate_candidates_status", "status"),
    )


class BusinessMerge(Base):
    __tablename__ = "business_merges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    surviving_business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False
    )
    merged_business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    merged_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    merged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    merged_by: Mapped[str] = mapped_column(String(160), nullable=False)


class AreaCache(TimestampMixin, Base):
    __tablename__ = "area_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_query: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    south: Mapped[float] = mapped_column(Float, nullable=False)
    west: Mapped[float] = mapped_column(Float, nullable=False)
    north: Mapped[float] = mapped_column(Float, nullable=False)
    east: Mapped[float] = mapped_column(Float, nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("normalized_query", "provider", name="uq_area_query_provider"),
    )


class ExportLog(Base):
    __tablename__ = "export_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workbook_source: Mapped[str] = mapped_column(Text, nullable=False)
    workbook_output: Mapped[str | None] = mapped_column(Text)
    batch_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    exported_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_existing_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_invalid_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[ExportStatus] = mapped_column(
        Enum(
            ExportStatus, name="export_status", values_callable=lambda obj: [e.value for e in obj]
        ),
        default=ExportStatus.PENDING,
        nullable=False,
    )
    error_type: Mapped[str | None] = mapped_column(String(160))
    error_message: Mapped[str | None] = mapped_column(Text)
    exported_business_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class ReviewEvent(Base):
    __tablename__ = "review_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    business: Mapped[Business] = relationship(back_populates="review_events")
    __table_args__ = (Index("ix_review_events_business_created", "business_id", "created_at"),)


__all__ = [
    "AreaCache",
    "Base",
    "Business",
    "BusinessMerge",
    "BusinessSearchRun",
    "DuplicateCandidate",
    "DuplicateMatchType",
    "DuplicateStatus",
    "ExportLog",
    "ExportStatus",
    "QualificationStatus",
    "ReviewEvent",
    "ReviewStatus",
    "SearchRun",
    "SearchStatus",
    "WebsiteCheck",
    "WebsiteCheckStatus",
]

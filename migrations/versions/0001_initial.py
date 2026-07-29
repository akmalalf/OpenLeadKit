"""Initial complete MVP schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the immutable schema baseline for OpenLeadKit 0.1.0."""
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "area_cache",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("query", sa.String(length=300), nullable=False),
        sa.Column("normalized_query", postgresql.CITEXT(), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=False),
        sa.Column("south", sa.Float(), nullable=False),
        sa.Column("west", sa.Float(), nullable=False),
        sa.Column("north", sa.Float(), nullable=False),
        sa.Column("east", sa.Float(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column(
            "raw_response",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalized_query",
            "provider",
            name="uq_area_query_provider",
        ),
    )

    op.create_table(
        "businesses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("osm_type", sa.String(length=16), nullable=False),
        sa.Column("osm_id", sa.BigInteger(), nullable=False),
        sa.Column("business_name", postgresql.CITEXT(), nullable=False),
        sa.Column("normalized_name", postgresql.CITEXT(), nullable=False),
        sa.Column("category_key", sa.String(length=80), nullable=False),
        sa.Column("category_label", sa.String(length=160), nullable=False),
        sa.Column("city", postgresql.CITEXT(), nullable=True),
        sa.Column("district", postgresql.CITEXT(), nullable=True),
        sa.Column("province", postgresql.CITEXT(), nullable=True),
        sa.Column("postcode", sa.String(length=32), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("normalized_domain", postgresql.CITEXT(), nullable=True),
        sa.Column("phone", sa.String(length=300), nullable=True),
        sa.Column("normalized_phone", sa.String(length=80), nullable=True),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("instagram", sa.String(length=300), nullable=True),
        sa.Column("opening_hours", sa.String(length=500), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column(
            "review_status",
            sa.Enum(
                "New",
                "Reviewed",
                "Approved",
                "Rejected",
                "Exported",
                name="review_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "qualification_status",
            sa.Enum(
                "Unknown",
                "High",
                "Medium",
                "Low",
                "Not Qualified",
                name="qualification_status",
            ),
            nullable=False,
        ),
        sa.Column("raw_notes", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "latitude BETWEEN -90 AND 90",
            name="ck_business_latitude",
        ),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180",
            name="ck_business_longitude",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "osm_type",
            "osm_id",
            name="uq_business_osm_identity",
        ),
    )
    op.create_index(
        "ix_business_category_key",
        "businesses",
        ["category_key"],
        unique=False,
    )
    op.create_index("ix_business_city", "businesses", ["city"], unique=False)
    op.create_index(
        "ix_business_first_seen_at",
        "businesses",
        ["first_seen_at"],
        unique=False,
    )
    op.create_index(
        "ix_business_last_seen_at",
        "businesses",
        ["last_seen_at"],
        unique=False,
    )
    op.create_index(
        "ix_business_normalized_domain",
        "businesses",
        ["normalized_domain"],
        unique=False,
    )
    op.create_index(
        "ix_business_normalized_name",
        "businesses",
        ["normalized_name"],
        unique=False,
    )
    op.create_index(
        "ix_business_normalized_name_trgm",
        "businesses",
        ["normalized_name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"normalized_name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_business_normalized_phone",
        "businesses",
        ["normalized_phone"],
        unique=False,
    )
    op.create_index(
        "ix_business_qualification_status",
        "businesses",
        ["qualification_status"],
        unique=False,
    )
    op.create_index(
        "ix_business_review_status",
        "businesses",
        ["review_status"],
        unique=False,
    )

    op.create_table(
        "export_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workbook_source", sa.Text(), nullable=False),
        sa.Column("workbook_output", sa.Text(), nullable=True),
        sa.Column("batch_id", sa.String(length=100), nullable=False),
        sa.Column("exported_count", sa.Integer(), nullable=False),
        sa.Column("skipped_existing_count", sa.Integer(), nullable=False),
        sa.Column("skipped_invalid_count", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "Pending",
                "Completed",
                "Failed",
                name="export_status",
            ),
            nullable=False,
        ),
        sa.Column("error_type", sa.String(length=160), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "exported_business_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id"),
    )

    op.create_table(
        "search_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("category_key", sa.String(length=80), nullable=False),
        sa.Column("category_label", sa.String(length=160), nullable=False),
        sa.Column("area_query", sa.String(length=300), nullable=False),
        sa.Column("area_display_name", sa.String(length=500), nullable=True),
        sa.Column("south", sa.Float(), nullable=False),
        sa.Column("west", sa.Float(), nullable=False),
        sa.Column("north", sa.Float(), nullable=False),
        sa.Column("east", sa.Float(), nullable=False),
        sa.Column("maximum_results", sa.Integer(), nullable=False),
        sa.Column("generated_query", sa.Text(), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "Pending",
                "Running",
                "Completed",
                "Failed",
                "Cancelled",
                name="search_status",
            ),
            nullable=False,
        ),
        sa.Column("total_received", sa.Integer(), nullable=False),
        sa.Column("total_created", sa.Integer(), nullable=False),
        sa.Column("total_updated", sa.Integer(), nullable=False),
        sa.Column("total_exact_duplicates", sa.Integer(), nullable=False),
        sa.Column("total_possible_duplicates", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_type", sa.String(length=160), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "raw_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "south < north AND west < east",
            name="ck_search_runs_bbox_order",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_search_runs_created_at",
        "search_runs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_search_runs_query_hash",
        "search_runs",
        ["query_hash"],
        unique=False,
    )
    op.create_index(
        "ix_search_runs_status",
        "search_runs",
        ["status"],
        unique=False,
    )

    op.create_table(
        "business_merges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("surviving_business_id", sa.UUID(), nullable=False),
        sa.Column("merged_business_id", sa.UUID(), nullable=False),
        sa.Column(
            "merged_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("merged_by", sa.String(length=160), nullable=False),
        sa.ForeignKeyConstraint(
            ["surviving_business_id"],
            ["businesses.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "business_search_runs",
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("search_run_id", sa.UUID(), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "raw_element",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["search_run_id"],
            ["search_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("business_id", "search_run_id"),
    )

    op.create_table(
        "duplicate_candidates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("candidate_business_id", sa.UUID(), nullable=False),
        sa.Column(
            "match_type",
            sa.Enum(
                "OSM Identity",
                "Domain",
                "Phone",
                "Name and City",
                name="duplicate_match_type",
            ),
            nullable=False,
        ),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "Pending",
                "Keep Both",
                "Merge",
                "Ignore Candidate",
                "Resolved",
                name="duplicate_status",
            ),
            nullable=False,
        ),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "business_id < candidate_business_id",
            name="ck_duplicate_canonical_pair",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "candidate_business_id",
            name="uq_duplicate_candidate_pair",
        ),
    )
    op.create_index(
        "ix_duplicate_candidates_status",
        "duplicate_candidates",
        ["status"],
        unique=False,
    )

    op.create_table(
        "review_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("previous_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_review_events_business_created",
        "review_events",
        ["business_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "website_checks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("requested_url", sa.Text(), nullable=False),
        sa.Column("checked_url", sa.Text(), nullable=True),
        sa.Column("final_url", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=160), nullable=True),
        sa.Column("response_bytes", sa.Integer(), nullable=True),
        sa.Column("page_title", sa.String(length=500), nullable=True),
        sa.Column("https_enabled", sa.Boolean(), nullable=True),
        sa.Column("mobile_viewport_found", sa.Boolean(), nullable=True),
        sa.Column("contact_page_url", sa.Text(), nullable=True),
        sa.Column("about_page_url", sa.Text(), nullable=True),
        sa.Column("public_email", postgresql.CITEXT(), nullable=True),
        sa.Column("public_phone", sa.String(length=300), nullable=True),
        sa.Column("whatsapp_url", sa.Text(), nullable=True),
        sa.Column("instagram_url", sa.Text(), nullable=True),
        sa.Column("robots_allowed", sa.Boolean(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "Pending",
                "Completed",
                "Blocked",
                "Failed",
                name="website_check_status",
            ),
            nullable=False,
        ),
        sa.Column("error_type", sa.String(length=160), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_website_checks_business_checked",
        "website_checks",
        ["business_id", "checked_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove only objects created by the 0.1.0 schema baseline."""
    op.drop_table("website_checks")
    op.drop_table("review_events")
    op.drop_table("duplicate_candidates")
    op.drop_table("business_search_runs")
    op.drop_table("business_merges")
    op.drop_table("search_runs")
    op.drop_table("export_logs")
    op.drop_table("businesses")
    op.drop_table("area_cache")

    for enum_name in (
        "search_status",
        "review_status",
        "qualification_status",
        "website_check_status",
        "duplicate_match_type",
        "duplicate_status",
        "export_status",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")

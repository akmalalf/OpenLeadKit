"""Operational audit and failure history."""

from __future__ import annotations

from math import ceil
from pathlib import Path

import streamlit as st

from openleadkit.config import get_settings
from openleadkit.models import ExportLog
from openleadkit.repositories import LeadViewRepository
from openleadkit.services.excel_exporter import read_exported_rows
from openleadkit.ui.common import db_session, format_error, section_header, setup_page

EXPORT_PAGE_SIZES = (10, 25, 50)
EXPORTED_ROW_PAGE_SIZES = (10, 25, 50, 100)


@st.cache_data(ttl=300, max_entries=50, show_spinner=False)
def _cached_exported_rows(
    path: str,
    file_modified_ns: int,
    batch_id: str,
    offset: int,
    limit: int,
) -> tuple[dict[str, object], ...]:
    """Cache bounded workbook pages and invalidate them when the file changes."""
    _ = file_modified_ns
    return read_exported_rows(Path(path), batch_id, offset=offset, limit=limit)


def _resolve_export_file(
    stored_output: str | None,
    *,
    project_root: Path,
    export_directory: Path,
) -> Path | None:
    """Resolve a recorded export only when it is a local XLSX inside the export directory."""
    if not stored_output:
        return None
    recorded = Path(stored_output)
    candidate = recorded if recorded.is_absolute() else project_root / recorded
    resolved = candidate.resolve()
    allowed_root = export_directory.resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError:
        return None
    if resolved.suffix.casefold() != ".xlsx" or not resolved.is_file():
        return None
    return resolved


def _format_export_choice(export_log: ExportLog) -> str:
    timestamp = export_log.exported_at or export_log.created_at
    return f"{export_log.batch_id} · {timestamp:%Y-%m-%d %H:%M} · {export_log.status.value}"


def _export_history_summary(export_rows: list[ExportLog]) -> list[dict[str, object]]:
    """Build a browser-safe summary without sending local workbook paths to the frontend."""
    return [
        {
            "Time": row.exported_at or row.created_at,
            "Batch": row.batch_id,
            "Status": row.status.value,
            "Exported": row.exported_count,
            "Skipped existing": row.skipped_existing_count,
            "Skipped invalid": row.skipped_invalid_count,
            "Error": row.error_message,
        }
        for row in export_rows
    ]


def _render_current_business_fallback(
    views: LeadViewRepository,
    export_log: ExportLog,
    *,
    page: int,
    page_size: int,
) -> None:
    entries, _ = views.exported_business_page(export_log, page, page_size)
    st.caption(
        "The workbook file is unavailable. These values come from the current database record "
        "and may differ from the original export."
    )
    st.dataframe(
        [
            {
                "Business ID": entry.business_id,
                "Business Name": (
                    entry.business.business_name if entry.business is not None else None
                ),
                "Category": entry.business.category_label if entry.business is not None else None,
                "City": entry.business.city if entry.business is not None else None,
                "Address": entry.business.address if entry.business is not None else None,
                "Source URL": entry.business.source_url if entry.business is not None else None,
                "Website URL": entry.business.website_url if entry.business is not None else None,
                "Phone": entry.business.phone if entry.business is not None else None,
                "Email": entry.business.email if entry.business is not None else None,
                "Record": "Available" if entry.business is not None else "No longer available",
            }
            for entry in entries
        ],
        column_config={
            "Source URL": st.column_config.LinkColumn("Source URL"),
            "Website URL": st.column_config.LinkColumn("Website URL"),
        },
        hide_index=True,
        width="stretch",
    )


def _render_export_details(
    views: LeadViewRepository,
    export_log: ExportLog,
    *,
    project_root: Path,
    export_directory: Path,
) -> None:
    section_header(
        "Exported lead data",
        f"Batch {export_log.batch_id}",
        f"{export_log.exported_count} EXPORTED",
    )
    export_file = _resolve_export_file(
        export_log.workbook_output,
        project_root=project_root,
        export_directory=export_directory,
    )
    if export_file is not None:
        st.download_button(
            "Download workbook",
            data=export_file.read_bytes,
            file_name=export_file.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_export_{export_log.id}",
            icon=":material/download:",
            on_click="ignore",
        )
    elif export_log.workbook_output:
        st.warning(
            "The recorded workbook is missing or outside the configured export directory. "
            "The audit record is still available."
        )

    total_rows = max(export_log.exported_count, len(export_log.exported_business_ids))
    if total_rows == 0:
        st.info("This batch does not contain exported lead rows.")
        return

    controls = st.columns([1, 1, 3])
    page_size = controls[0].selectbox(
        "Rows per page",
        EXPORTED_ROW_PAGE_SIZES,
        key=f"exported_rows_size_{export_log.id}",
    )
    page_count = max(1, ceil(total_rows / page_size))
    page = int(
        controls[1].number_input(
            "Data page",
            min_value=1,
            max_value=page_count,
            value=1,
            step=1,
            key=f"exported_rows_page_{export_log.id}_{page_size}_{total_rows}",
        )
    )
    controls[2].caption(f"Showing page {page} of {page_count} · {total_rows} exported lead records")

    if export_file is None:
        _render_current_business_fallback(
            views,
            export_log,
            page=page,
            page_size=page_size,
        )
        return

    try:
        rows = _cached_exported_rows(
            str(export_file),
            export_file.stat().st_mtime_ns,
            export_log.batch_id,
            (page - 1) * page_size,
            page_size,
        )
    except Exception as exc:
        st.warning(
            "The exact workbook rows could not be read. Current database values are shown "
            f"instead. {format_error(exc)}"
        )
        _render_current_business_fallback(
            views,
            export_log,
            page=page,
            page_size=page_size,
        )
        return

    if not rows:
        st.warning("No matching rows were found for this batch in the recorded workbook.")
        return
    st.caption("These are the exact values stored in the exported workbook.")
    st.dataframe(
        list(rows),
        column_config={
            "Imported At": st.column_config.DatetimeColumn(
                "Imported At",
                format="YYYY-MM-DD HH:mm:ss",
            ),
            "Source URL": st.column_config.LinkColumn("Source URL"),
            "Website URL": st.column_config.LinkColumn("Website URL"),
            "Latitude": st.column_config.NumberColumn("Latitude", format="%.6f"),
            "Longitude": st.column_config.NumberColumn("Longitude", format="%.6f"),
        },
        hide_index=True,
        width="stretch",
    )


def _render_export_history(views: LeadViewRepository) -> None:
    settings = get_settings()
    total_exports = views.export_history_count()
    if total_exports == 0:
        st.info("No export history has been recorded yet.")
        return

    controls = st.columns([1, 1, 3])
    page_size = controls[0].selectbox(
        "Files per page",
        EXPORT_PAGE_SIZES,
        key="export_history_page_size",
    )
    page_count = max(1, ceil(total_exports / page_size))
    page = int(
        controls[1].number_input(
            "File page",
            min_value=1,
            max_value=page_count,
            value=1,
            step=1,
            key=f"export_history_page_{page_size}_{total_exports}",
        )
    )
    controls[2].caption(f"Showing page {page} of {page_count} · {total_exports} export records")
    export_rows = views.export_history_page(page, page_size)
    st.dataframe(
        _export_history_summary(export_rows),
        column_config={
            "Time": st.column_config.DatetimeColumn("Time", format="YYYY-MM-DD HH:mm:ss"),
        },
        hide_index=True,
        width="stretch",
    )

    rows_by_id = {str(row.id): row for row in export_rows}
    selected_id = st.selectbox(
        "Inspect an export batch",
        list(rows_by_id),
        format_func=lambda row_id: _format_export_choice(rows_by_id[row_id]),
        key=f"selected_export_{page}_{page_size}",
    )
    _render_export_details(
        views,
        rows_by_id[selected_id],
        project_root=settings.project_root,
        export_directory=settings.excel_output,
    )


def render() -> None:
    setup_page(
        "Audit trail",
        "History",
        "Review searches, failures, website checks, duplicate decisions, reviews, and exports.",
    )
    section_header(
        "Recorded events",
        "Switch views to inspect each operational trail. Database credentials are never shown.",
        "READ ONLY",
    )
    tabs = st.tabs(
        ["Searches", "Website Checks", "Reviews", "Duplicates", "Exports"],
        key="history_view",
        on_change="rerun",
    )
    with db_session() as session:
        views = LeadViewRepository(session)
        if tabs[0].open:
            with tabs[0]:
                search_rows = views.search_history()
                st.dataframe(
                    [
                        {
                            "Time": row.created_at,
                            "Category": row.category_label,
                            "Area": row.area_display_name or row.area_query,
                            "Status": row.status.value,
                            "Received": row.total_received,
                            "Created": row.total_created,
                            "Error": row.error_message,
                        }
                        for row in search_rows
                    ],
                    width="stretch",
                )
        elif tabs[1].open:
            with tabs[1]:
                website_rows = views.website_history()
                st.dataframe(
                    [
                        {
                            "Time": row.checked_at or row.created_at,
                            "Business ID": row.business_id,
                            "URL": row.requested_url,
                            "Status": row.status.value,
                            "HTTP": row.http_status,
                            "Error": row.error_message,
                        }
                        for row in website_rows
                    ],
                    width="stretch",
                )
        elif tabs[2].open:
            with tabs[2]:
                review_rows = views.all_review_events()
                st.dataframe(
                    [
                        {
                            "Time": row.created_at,
                            "Business ID": row.business_id,
                            "Type": row.event_type,
                            "Before": row.previous_value,
                            "After": row.new_value,
                            "Notes": row.notes,
                        }
                        for row in review_rows
                    ],
                    width="stretch",
                )
        elif tabs[3].open:
            with tabs[3]:
                duplicate_rows = views.duplicate_history()
                st.dataframe(
                    [
                        {
                            "Time": row.created_at,
                            "Left": row.business_id,
                            "Right": row.candidate_business_id,
                            "Reason": row.match_type.value,
                            "Score": row.similarity_score,
                            "Status": row.status.value,
                            "Notes": row.decision_notes,
                        }
                        for row in duplicate_rows
                    ],
                    width="stretch",
                )
        elif tabs[4].open:
            with tabs[4]:
                _render_export_history(views)

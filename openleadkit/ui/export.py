"""Verified CRM workbook export page."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from math import ceil
from pathlib import Path

import streamlit as st

from openleadkit.config import get_settings
from openleadkit.models import (
    Business,
    ExportLog,
    ExportStatus,
    ReviewEvent,
    ReviewStatus,
)
from openleadkit.repositories import LeadViewRepository
from openleadkit.services.excel_exporter import (
    ExportRecord,
    export_workbook,
    generate_batch_id,
    inspect_workbook,
)
from openleadkit.ui.common import (
    db_session,
    empty_state,
    format_error,
    section_header,
    setup_page,
)

EXPORT_BATCH_PAGE_SIZES = (10, 25, 50)
EXPORT_PREVIEW_PAGE_SIZES = (25, 50, 100)
SELECTED_BATCHES_KEY = "crm_export_selected_batches"


def _format_export_batch(export_log: ExportLog) -> str:
    exported_at = export_log.exported_at or export_log.created_at
    return (
        f"{export_log.batch_id} · {exported_at:%Y-%m-%d %H:%M} · {export_log.exported_count} leads"
    )


def _selected_batch_ids() -> list[uuid.UUID]:
    selected_ids: list[uuid.UUID] = []
    raw_values = st.session_state.get(SELECTED_BATCHES_KEY, [])
    if not isinstance(raw_values, list):
        return selected_ids
    for raw_value in raw_values:
        try:
            selected_ids.append(uuid.UUID(str(raw_value)))
        except (ValueError, TypeError, AttributeError):
            continue
    return selected_ids


def _render_export_source_selector(
    views: LeadViewRepository,
) -> tuple[bool, list[ExportLog]]:
    section_header(
        "Choose export sources",
        "Combine the current approval queue with any previously completed export batches.",
        "SELECT",
    )
    include_approved = st.toggle(
        "Include currently approved leads",
        value=True,
        key="crm_export_include_approved",
        help="Approved leads are marked Exported only if they are written to the new workbook.",
    )

    total_batches = views.exportable_history_count()
    if total_batches:
        controls = st.columns([1, 1, 3])
        page_size = controls[0].selectbox(
            "Batches per page",
            EXPORT_BATCH_PAGE_SIZES,
            key="crm_export_batch_page_size",
        )
        page_count = max(1, ceil(total_batches / page_size))
        page = int(
            controls[1].number_input(
                "Batch page",
                min_value=1,
                max_value=page_count,
                value=1,
                step=1,
                key=f"crm_export_batch_page_{page_size}_{total_batches}",
            )
        )
        controls[2].caption(
            f"Showing page {page} of {page_count} · {total_batches} completed batches"
        )
        page_rows = views.exportable_history_page(page, page_size)
        st.dataframe(
            [
                {
                    "Time": row.exported_at or row.created_at,
                    "Batch": row.batch_id,
                    "Exported leads": row.exported_count,
                    "File": Path(row.workbook_output).name if row.workbook_output else None,
                }
                for row in page_rows
            ],
            column_config={
                "Time": st.column_config.DatetimeColumn(
                    "Time",
                    format="YYYY-MM-DD HH:mm:ss",
                ),
            },
            hide_index=True,
            width="stretch",
        )
        page_rows_by_id = {str(row.id): row for row in page_rows}
        additions = st.multiselect(
            "Choose batches from this page",
            list(page_rows_by_id),
            format_func=lambda row_id: _format_export_batch(page_rows_by_id[row_id]),
            key=f"crm_export_batch_choices_{page}_{page_size}",
        )
        if st.button(
            "Add selected batches",
            key=f"crm_export_add_batches_{page}_{page_size}",
            icon=":material/add:",
            disabled=not additions,
        ):
            selected = {str(item) for item in _selected_batch_ids()}
            selected.update(additions)
            st.session_state[SELECTED_BATCHES_KEY] = sorted(selected)
            st.rerun()
    else:
        st.caption("No completed historical export batches are available yet.")

    selected_logs = views.export_logs_by_ids(_selected_batch_ids())
    valid_selected_ids = [str(export_log.id) for export_log in selected_logs]
    st.session_state[SELECTED_BATCHES_KEY] = valid_selected_ids
    if selected_logs:
        st.caption(
            f"{len(selected_logs)} historical batch"
            f"{'es' if len(selected_logs) != 1 else ''} selected for combination."
        )
        st.dataframe(
            [
                {
                    "Batch": row.batch_id,
                    "Time": row.exported_at or row.created_at,
                    "Exported leads": row.exported_count,
                }
                for row in selected_logs
            ],
            column_config={
                "Time": st.column_config.DatetimeColumn(
                    "Time",
                    format="YYYY-MM-DD HH:mm:ss",
                ),
            },
            hide_index=True,
            width="stretch",
        )
        remove_controls = st.columns(
            [3, 1, 1],
            gap="small",
            vertical_alignment="bottom",
        )
        selected_by_id = {str(row.id): row for row in selected_logs}
        selection_widget_key = uuid.uuid5(
            uuid.NAMESPACE_URL,
            "|".join(valid_selected_ids),
        ).hex[:12]
        remove_id = remove_controls[0].selectbox(
            "Remove one selected batch",
            list(selected_by_id),
            format_func=lambda row_id: _format_export_batch(selected_by_id[row_id]),
            key=f"crm_export_remove_batch_{selection_widget_key}",
        )
        if remove_controls[1].button(
            "Remove",
            icon=":material/remove:",
            key="crm_export_remove_selected_batch",
            width="stretch",
        ):
            st.session_state[SELECTED_BATCHES_KEY] = [
                row_id for row_id in valid_selected_ids if row_id != remove_id
            ]
            st.rerun()
        if remove_controls[2].button(
            "Clear all",
            icon=":material/clear_all:",
            key="crm_export_clear_batches",
            width="stretch",
        ):
            st.session_state[SELECTED_BATCHES_KEY] = []
            st.rerun()

    st.caption(
        "Historical batches use the latest stored business values. "
        "Use History → Exports to inspect the exact original workbook values."
    )
    return include_approved, selected_logs


def _build_export_records(businesses: tuple[Business, ...]) -> list[ExportRecord]:
    records: list[ExportRecord] = []
    for business in businesses:
        latest_search = max(
            (link.search_run for link in business.search_runs),
            key=lambda search_run: search_run.created_at,
            default=None,
        )
        records.append(
            ExportRecord(
                business_id=business.id,
                business_name=business.business_name,
                category=business.category_label,
                city=business.city,
                address=business.address,
                source_url=business.source_url,
                website_url=business.website_url,
                phone=business.phone,
                email=business.email,
                instagram=business.instagram,
                opening_hours=business.opening_hours,
                latitude=business.latitude,
                longitude=business.longitude,
                search_query=(
                    f"{latest_search.category_label} — {latest_search.area_query}"
                    if latest_search
                    else business.category_label
                ),
                raw_notes=(
                    f"Qualification: {business.qualification_status.value}. "
                    f"{business.raw_notes or ''}"
                ).strip(),
            )
        )
    return records


def _render_export_preview(records: list[ExportRecord], batch_id: str) -> None:
    section_header(
        "Combined export preview",
        "Repeated business IDs appear once; normal duplicate checks still run during export.",
        f"{len(records)} READY",
    )
    st.metric("Unique business records selected", len(records))
    st.code(batch_id)
    controls = st.columns([1, 1, 3])
    page_size = controls[0].selectbox(
        "Preview rows per page",
        EXPORT_PREVIEW_PAGE_SIZES,
        key="crm_export_preview_page_size",
    )
    page_count = max(1, ceil(len(records) / page_size))
    page = int(
        controls[1].number_input(
            "Preview page",
            min_value=1,
            max_value=page_count,
            value=1,
            step=1,
            key=f"crm_export_preview_page_{page_size}_{len(records)}",
        )
    )
    controls[2].caption(f"Showing page {page} of {page_count} · {len(records)} unique leads")
    start = (page - 1) * page_size
    st.dataframe(
        [
            {
                "Name": record.business_name,
                "Category": record.category,
                "City": record.city,
                "Phone": record.phone,
                "Website": record.website_url,
            }
            for record in records[start : start + page_size]
        ],
        column_config={
            "Website": st.column_config.LinkColumn("Website"),
        },
        hide_index=True,
        width="stretch",
    )


def render() -> None:
    setup_page(
        "Controlled handoff",
        "CRM Export",
        "Combine current approvals and selected historical batches in a generated workbook "
        "or an optional custom template. Custom source workbooks are never overwritten.",
    )
    settings = get_settings()
    source = settings.excel_input
    template_source = source if source.is_file() else None
    if source.exists() and template_source is None:
        st.error(
            f"The configured workbook path is not a file: {source}. "
            "Update EXCEL_INPUT_PATH and restart the application."
        )
        return
    if template_source is None:
        st.info(
            "No custom workbook was found. OpenLeadKit will create a new XLSX file "
            "with a formatted Raw Import worksheet."
        )
    else:
        try:
            inspection = inspect_workbook(template_source)
            st.success("The custom workbook is compatible.")
            st.caption(
                f"Sheet: {inspection.raw_import_name} · header row {inspection.header_row} · "
                f"first empty row {inspection.first_empty_row}"
            )
            with st.expander("Current column mapping"):
                st.write(list(inspection.columns))
        except Exception as exc:
            st.error(format_error(exc))
            return
    with db_session() as session:
        views = LeadViewRepository(session)
        include_approved, selected_logs = _render_export_source_selector(views)
        selection = views.export_business_selection(
            selected_logs,
            include_approved=include_approved,
        )
        if selection.missing_historical_count:
            st.warning(
                f"{selection.missing_historical_count} historical business record(s) are no "
                "longer available and cannot be included."
            )
        if not selection.businesses:
            empty_state(
                "No export sources selected",
                "Include the current approval queue or add one or more historical batches.",
                "CSV",
            )
            return
        records = _build_export_records(selection.businesses)
        now = datetime.now(UTC).astimezone()
        batch_id = generate_batch_id(records, now)
        _render_export_preview(records, batch_id)
        if st.button("Export combined selection", type="primary"):
            log = ExportLog(
                workbook_source=(
                    str(template_source)
                    if template_source is not None
                    else "Generated by OpenLeadKit"
                ),
                batch_id=batch_id,
                status=ExportStatus.PENDING,
            )
            session.add(log)
            session.flush()
            try:
                result = export_workbook(
                    template_source,
                    settings.excel_output,
                    records,
                    now=now,
                )
                log.workbook_output = str(result.output_path)
                log.exported_count = len(result.exported_ids)
                log.skipped_existing_count = result.skipped_existing
                log.skipped_invalid_count = result.skipped_invalid
                log.exported_business_ids = [str(item) for item in result.exported_ids]
                log.status = ExportStatus.COMPLETED
                log.exported_at = datetime.now(UTC)
                for business in selection.businesses:
                    if (
                        business.id in result.exported_ids
                        and business.id in selection.approved_business_ids
                    ):
                        previous = business.review_status.value
                        business.review_status = ReviewStatus.EXPORTED
                        session.add(
                            ReviewEvent(
                                business_id=business.id,
                                event_type="Export",
                                previous_value=previous,
                                new_value=ReviewStatus.EXPORTED.value,
                                notes=result.batch_id,
                            )
                        )
                st.success(f"Export completed: `{result.output_path}`")
                st.download_button(
                    "Download exported workbook",
                    result.output_path.read_bytes,
                    file_name=result.output_path.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    on_click="ignore",
                )
            except Exception as exc:
                log.status = ExportStatus.FAILED
                log.error_type = type(exc).__name__
                log.error_message = str(exc)
                st.error(format_error(exc))

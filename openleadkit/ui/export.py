"""Verified CRM workbook export page."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from openleadkit.config import get_settings
from openleadkit.models import (
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


def render() -> None:
    setup_page(
        "Controlled handoff",
        "CRM Export",
        "Export only approved leads that have not been exported. "
        "The source workbook is never overwritten.",
    )
    settings = get_settings()
    source = settings.excel_input
    if not source.exists():
        empty_state(
            "Source workbook not found",
            f"Place the CRM workbook at {source}, then reload this page.",
            "XLSX",
        )
        return
    try:
        inspection = inspect_workbook(source)
        st.success("The workbook is compatible.")
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
        businesses = views.approved_businesses()
        if not businesses:
            empty_state(
                "Nothing is ready to export",
                "Approve qualified leads in Lead Review. They will appear in this queue.",
                "CSV",
            )
            return
        records: list[ExportRecord] = []
        for business in businesses:
            search_run = views.latest_search_for_business(business.id)
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
                        f"{search_run.category_label} — {search_run.area_query}"
                        if search_run
                        else business.category_label
                    ),
                    raw_notes=(
                        f"Qualification: {business.qualification_status.value}. "
                        f"{business.raw_notes or ''}"
                    ).strip(),
                )
            )
        now = datetime.now(UTC).astimezone()
        batch_id = generate_batch_id(records, now)
        section_header(
            "Export preview",
            "Only the rows shown below will be written to a timestamped workbook copy.",
            f"{len(records)} READY",
        )
        st.metric("Leads ready for export", len(records))
        st.code(batch_id)
        st.dataframe(
            [
                {
                    "Name": record.business_name,
                    "Category": record.category,
                    "City": record.city,
                    "Phone": record.phone,
                    "Website": record.website_url,
                }
                for record in records
            ],
            width="stretch",
        )
        if st.button("Export to Raw Import", type="primary"):
            log = ExportLog(
                workbook_source=str(source),
                batch_id=batch_id,
                status=ExportStatus.PENDING,
            )
            session.add(log)
            session.flush()
            try:
                result = export_workbook(source, settings.excel_output, records, now=now)
                log.workbook_output = str(result.output_path)
                log.exported_count = len(result.exported_ids)
                log.skipped_existing_count = result.skipped_existing
                log.skipped_invalid_count = result.skipped_invalid
                log.exported_business_ids = [str(item) for item in result.exported_ids]
                log.status = ExportStatus.COMPLETED
                log.exported_at = datetime.now(UTC)
                for business in businesses:
                    if business.id in result.exported_ids:
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
                    result.output_path.read_bytes(),
                    file_name=result.output_path.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            except Exception as exc:
                log.status = ExportStatus.FAILED
                log.error_type = type(exc).__name__
                log.error_message = str(exc)
                st.error(format_error(exc))

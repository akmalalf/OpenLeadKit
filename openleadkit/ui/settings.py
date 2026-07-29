"""Read-only application configuration page."""

from __future__ import annotations

import streamlit as st

from openleadkit.config import get_settings
from openleadkit.ui.common import section_header, setup_page


def render() -> None:
    setup_page(
        "Application configuration",
        "Settings",
        "Review the active non-secret configuration. Edit `.env` and restart OpenLeadKit "
        "to change these values.",
    )
    settings = get_settings()
    section_header(
        "Runtime values",
        "These values are loaded from the environment and cannot be edited in the UI.",
        "READ ONLY",
    )
    fields: dict[str, object] = {
        "project_url": str(settings.app_project_url),
        "overpass_endpoint": str(settings.overpass_api_url),
        "nominatim_endpoint": str(settings.nominatim_api_url),
        "request_delay_seconds": settings.http_per_domain_delay_seconds,
        "request_timeout_seconds": settings.http_read_timeout_seconds,
        "response_size_limit": settings.http_max_response_bytes,
        "default_result_limit": settings.default_result_limit,
        "duplicate_threshold": settings.duplicate_name_threshold,
        "excel_input_path": str(settings.excel_input_path),
        "excel_output_directory": str(settings.excel_output_dir),
        "display_timezone": settings.app_timezone,
    }
    columns = st.columns(2)
    for index, (key, default) in enumerate(fields.items()):
        column = columns[index % len(columns)]
        label = key.replace("_", " ").capitalize()
        if isinstance(default, bool):
            column.checkbox(label, value=default, disabled=True)
        elif isinstance(default, (int, float)):
            column.number_input(label, value=default, disabled=True)
        else:
            column.text_input(label, value=str(default), max_chars=500, disabled=True)
    st.info(
        "Edit `.env` to change configuration. Database passwords are intentionally not displayed."
    )

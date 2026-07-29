"""OpenLeadKit Streamlit entry point."""

from pathlib import Path

import streamlit as st

from openleadkit import __version__
from openleadkit.logging_config import configure_logging
from openleadkit.ui.common import (
    CSS,
    load_settings_or_stop,
    render_sidebar_footer,
)

ASSET_DIRECTORY = Path(__file__).resolve().parent / "openleadkit" / "ui" / "assets"

st.set_page_config(
    page_title="OpenLeadKit · Local lead workspace",
    page_icon=str(ASSET_DIRECTORY / "openleadkit-icon.svg"),
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get help": "https://github.com/akmalalf/OpenLeadKit#readme",
        "Report a bug": "https://github.com/akmalalf/OpenLeadKit/issues",
        "About": (
            "OpenLeadKit is an open-source toolkit for discovering, reviewing, "
            "qualifying, and exporting public local-business leads."
        ),
    },
)

st.logo(
    str(ASSET_DIRECTORY / "openleadkit-logo.svg"),
    size="large",
    icon_image=str(ASSET_DIRECTORY / "openleadkit-icon.svg"),
)
st.markdown(CSS, unsafe_allow_html=True)

if not Path(".env").exists():
    st.error("Configuration is missing. Copy `.env.example` to `.env`.")
    st.code("cp .env.example .env")
    st.stop()

settings = load_settings_or_stop()
configure_logging(settings.app_debug)

pages = {
    "Start": [
        st.Page(
            "pages/01_Dashboard.py",
            title="Dashboard",
            default=True,
        ),
        st.Page(
            "pages/02_Business_Search.py",
            title="Business Search",
        ),
        st.Page(
            "pages/03_Search_Results.py",
            title="Search Results",
        ),
    ],
    "Qualification": [
        st.Page(
            "pages/04_Lead_Review.py",
            title="Lead Review",
        ),
        st.Page(
            "pages/05_Duplicates.py",
            title="Duplicates",
        ),
        st.Page(
            "pages/06_CRM_Export.py",
            title="CRM Export",
        ),
    ],
    "Operations": [
        st.Page(
            "pages/07_History.py",
            title="History",
        ),
        st.Page(
            "pages/08_Settings.py",
            title="Settings",
        ),
    ],
}

navigation = st.navigation(pages, position="sidebar")
render_sidebar_footer(__version__)
navigation.run()

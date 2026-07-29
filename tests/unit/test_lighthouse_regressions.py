from pathlib import Path
from tomllib import loads
from xml.etree import ElementTree

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIRECTORY = PROJECT_ROOT / "openleadkit" / "ui" / "assets"


def test_streamlit_usage_telemetry_is_disabled() -> None:
    config = loads((PROJECT_ROOT / ".streamlit" / "config.toml").read_text())

    assert config["browser"]["gatherUsageStats"] is False


def test_brand_svgs_declare_intrinsic_dimensions() -> None:
    expected_dimensions = {
        "openleadkit-logo.svg": ("220", "44"),
        "openleadkit-icon.svg": ("44", "44"),
    }

    for filename, dimensions in expected_dimensions.items():
        root = ElementTree.parse(ASSET_DIRECTORY / filename).getroot()
        assert (root.attrib["width"], root.attrib["height"]) == dimensions


def test_sidebar_navigation_matches_original_expanded_structure() -> None:
    app_source = (PROJECT_ROOT / "app.py").read_text()

    assert "st.logo(" in app_source
    assert '"openleadkit-logo.svg"' in app_source
    assert 'size="large"' in app_source
    assert 'initial_sidebar_state="expanded"' in app_source
    assert '"Start": [' in app_source
    assert 'st.navigation(pages, position="sidebar")' in app_source
    assert "render_sidebar_footer(__version__)" in app_source

from unittest.mock import Mock
from urllib.parse import unquote
from xml.etree import ElementTree

import pytest
from pydantic import ValidationError

from openleadkit.config import Settings
from openleadkit.ui import common


class RerunSignal(BaseException):
    pass


def test_commit_happens_before_streamlit_rerun(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock()

    def rerun() -> None:
        raise RerunSignal

    monkeypatch.setattr(common.st, "rerun", rerun)
    with pytest.raises(RerunSignal):
        common.commit_and_rerun(session)
    session.commit.assert_called_once_with()


def test_validation_errors_do_not_echo_credential_input() -> None:
    secret = "DO_NOT_DISPLAY"
    with pytest.raises(ValidationError) as captured:
        Settings(database_url=f"mysql://user:{secret}@example.invalid/openleadkit")
    message = common.safe_validation_error(captured.value)
    assert secret not in message
    assert "database_url" in message
    assert "PostgreSQL" in message


def test_setup_page_escapes_display_text(monkeypatch: pytest.MonkeyPatch) -> None:
    markdown = Mock()
    monkeypatch.setattr(common.st, "markdown", markdown)

    common.setup_page(
        "<script>kicker</script>",
        "Leads <review>",
        "A & B",
    )

    rendered = markdown.call_args.args[0]
    assert "<script>kicker</script>" not in rendered
    assert "&lt;script&gt;kicker&lt;/script&gt;" in rendered
    assert "Leads &lt;review&gt;" in rendered
    assert "A &amp; B" in rendered


def test_setup_page_returns_page_action_click(monkeypatch: pytest.MonkeyPatch) -> None:
    heading = Mock()
    action = Mock()
    action.button.return_value = True
    monkeypatch.setattr(common.st, "columns", Mock(return_value=[heading, action]))
    monkeypatch.setattr(common.st, "markdown", Mock())

    clicked = common.setup_page(
        "Queue",
        "Lead Review",
        "Review one record.",
        action_label="How to use",
        action_key="review_help",
    )

    assert clicked is True
    heading.markdown.assert_called_once()
    action.button.assert_called_once_with(
        "How to use",
        key="review_help",
        use_container_width=True,
    )


def test_empty_state_escapes_display_text(monkeypatch: pytest.MonkeyPatch) -> None:
    markdown = Mock()
    monkeypatch.setattr(common.st, "markdown", markdown)

    common.empty_state("<No results>", "Try A & B", marker="<0>")

    rendered = markdown.call_args.args[0]
    assert "&lt;No results&gt;" in rendered
    assert "Try A &amp; B" in rendered
    assert "&lt;0&gt;" in rendered


def test_metric_grid_formats_numbers_and_escapes_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markdown = Mock()
    monkeypatch.setattr(common.st, "markdown", markdown)

    common.metric_grid([("<New>", 1234), ("Status", "A & B")])

    rendered = markdown.call_args.args[0]
    assert "&lt;New&gt;" in rendered
    assert "1,234" in rendered
    assert "A &amp; B" in rendered


def test_global_css_uses_streamlit_bundled_fonts_without_remote_imports() -> None:
    assert '[class*="st-"]' not in common.CSS
    assert "@import url(" not in common.CSS
    assert 'font-family:"Source Sans"' in common.CSS
    assert "Source Code Pro" not in common.CSS
    assert "font-family:ui-monospace" in common.CSS


def test_global_css_styles_sidebar_navigation_states() -> None:
    assert '[data-testid="stSidebarHeader"]' in common.CSS
    assert '[data-testid="stSidebarLogo"]' in common.CSS
    assert "SIDEBAR_LOGO_DATA_URI" not in common.CSS
    assert '[data-testid="stSidebarNav"] li a[aria-current="page"]' in common.CSS
    assert '[data-testid="stSidebarNav"] li a:focus-visible' in common.CSS
    assert '[data-testid="stSidebarNavSeparator"]' in common.CSS
    assert '[data-testid="stSidebarUserContent"]' in common.CSS
    assert 'a[href$="/Business_Search"]::before' in common.CSS
    assert 'a[href$="/Settings"]::before' in common.CSS
    assert "__OLK_ICON_" not in common.CSS
    assert "box-shadow:inset" not in common.CSS
    assert "translateX" not in common.CSS


def test_sidebar_lucide_icons_are_valid_inline_svgs() -> None:
    assert len(common.LUCIDE_SIDEBAR_ICONS) == 8

    for data_uri in common.LUCIDE_SIDEBAR_ICONS.values():
        assert data_uri.startswith("data:image/svg+xml,")
        svg = unquote(data_uri.removeprefix("data:image/svg+xml,"))
        assert ElementTree.fromstring(svg).tag.endswith("svg")


def test_sidebar_footer_escapes_version_and_keeps_original_project_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markdown = Mock()
    monkeypatch.setattr(common.st.sidebar, "markdown", markdown)

    common.render_sidebar_footer("<0.1.0>")

    rendered = markdown.call_args.args[0]
    assert "OpenLeadKit v&lt;0.1.0&gt;" in rendered
    assert "Data © OpenStreetMap contributors" in rendered
    assert "Open source · Apache-2.0" in rendered
    assert "<footer" in rendered


def test_section_header_uses_a_semantic_second_level_heading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markdown = Mock()
    monkeypatch.setattr(common.st, "markdown", markdown)

    common.section_header("Lead pipeline", "Current records", "CURRENT")

    rendered = markdown.call_args.args[0]
    assert '<h2 class="olk-section-title">Lead pipeline</h2>' in rendered


def test_database_engine_and_health_are_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = "postgresql+psycopg://user:secret@127.0.0.1/openleadkit_cache_test"
    engine = Mock()
    health = common.DatabaseHealth(
        version="PostgreSQL 16",
        database="openleadkit_cache_test",
        user="openleadkit_app",
        extensions=frozenset({"citext", "pg_trgm"}),
        migration_revision="0001_initial",
    )
    build_engine = Mock(return_value=engine)
    inspect_database = Mock(return_value=health)
    monkeypatch.setattr(common, "build_engine", build_engine)
    monkeypatch.setattr(common, "inspect_database", inspect_database)
    common.get_database_engine.clear()
    common.get_database_health.clear()

    try:
        assert common.get_database_engine(database_url) is engine
        assert common.get_database_engine(database_url) is engine
        assert common.get_database_health(database_url) == health
        assert common.get_database_health(database_url) == health
    finally:
        common.get_database_health.clear()
        common.get_database_engine.clear()

    build_engine.assert_called_once_with(database_url)
    inspect_database.assert_called_once_with(engine)

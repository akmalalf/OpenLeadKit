from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from openleadkit.ui import dashboard


def test_latest_search_table_has_headers_and_escapes_source_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markdown = Mock()
    monkeypatch.setattr(dashboard.st, "markdown", markdown)
    search = SimpleNamespace(
        category_label="<script>category</script>",
        area_display_name="A & B",
        area_query="unused",
        finished_at=datetime(2026, 7, 30, 9, 15, tzinfo=UTC),
        created_at=datetime(2026, 7, 30, 9, 0, tzinfo=UTC),
        total_created=12,
        total_updated=3,
    )

    dashboard._render_recent_searches((search,))

    rendered = markdown.call_args.args[0]
    assert '<table class="olk-search-table">' in rendered
    assert '<th scope="col">Category</th>' in rendered
    assert '<th scope="col">Completed</th>' in rendered
    assert "&lt;script&gt;category&lt;/script&gt;" in rendered
    assert "A &amp; B" in rendered
    assert "<script>category</script>" not in rendered
    assert "12" in rendered
    assert "created" in rendered

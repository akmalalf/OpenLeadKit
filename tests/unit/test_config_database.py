from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from openleadkit import database
from openleadkit.config import Settings
from openleadkit.database import inspect_database, validate_test_database_urls
from openleadkit.exceptions import ConfigurationError, DatabaseError
from openleadkit.services.search import advisory_lock_key


def make_settings(**values: object) -> Settings:
    base = {
        "database_url": "postgresql+psycopg://user:secret@127.0.0.1/openleadkit",
        "test_database_url": None,
    }
    base.update(values)
    return Settings.model_validate(base)


def test_database_url_is_masked() -> None:
    result = make_settings().masked_database_url
    assert "secret" not in result
    assert "user:***@" in result


def test_database_inspection_groups_server_metadata_into_one_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Mock()
    connection.execute.return_value.one.return_value = (
        "PostgreSQL 16.4",
        "openleadkit",
        "openleadkit_app",
        ["citext", "pg_trgm"],
    )
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    migration_context = Mock()
    migration_context.get_current_revision.return_value = "0001_initial"
    configure = Mock(return_value=migration_context)
    monkeypatch.setattr(database.MigrationContext, "configure", configure)

    health = inspect_database(engine)

    assert health.database == "openleadkit"
    assert health.extensions == frozenset({"citext", "pg_trgm"})
    assert health.migrations_current
    connection.execute.assert_called_once()
    query = str(connection.execute.call_args.args[0])
    assert "current_database()" in query
    assert "FROM pg_extension" in query
    configure.assert_called_once_with(connection)


def test_settings_require_postgresql_and_valid_limits() -> None:
    with pytest.raises(ValueError):
        Settings(database_url="sqlite:///local.db")
    with pytest.raises(ValueError):
        make_settings(default_result_limit=200, max_result_limit=100)


def test_safe_paths_block_traversal(tmp_path: Path) -> None:
    settings = make_settings()
    with pytest.raises(ConfigurationError):
        settings.safe_path(Path("../../etc/passwd"))


def test_destructive_database_safety() -> None:
    with pytest.raises(DatabaseError, match="not configured"):
        validate_test_database_urls(make_settings())
    with pytest.raises(DatabaseError, match="cannot equal"):
        validate_test_database_urls(
            make_settings(
                test_database_url="postgresql+psycopg://user:secret@127.0.0.1/openleadkit"
            )
        )
    with pytest.raises(DatabaseError, match="test"):
        validate_test_database_urls(
            make_settings(test_database_url="postgresql+psycopg://user:secret@127.0.0.1/sandbox")
        )
    safe = make_settings(
        test_database_url="postgresql+psycopg://user:secret@127.0.0.1/openleadkit_test"
    )
    assert validate_test_database_urls(safe).endswith("/openleadkit_test")


def test_advisory_lock_key_is_stable_signed_bigint() -> None:
    key = advisory_lock_key("f" * 64)
    assert key == -1


def test_initial_migration_is_self_contained() -> None:
    migration = (
        Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0001_initial.py"
    ).read_text(encoding="utf-8")

    assert "openleadkit.models" not in migration
    assert "Base.metadata" not in migration
    assert migration.count("op.create_table(") == 9
    assert migration.count("op.drop_table(") == 9

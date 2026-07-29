from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openleadkit.config import Settings, clear_settings_cache
from openleadkit.database import validate_test_database_urls
from openleadkit.exceptions import DatabaseError


@pytest.fixture
def integration_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("TEST_DATABASE_URL is not configured; database tests were safely skipped")
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://invalid:invalid@127.0.0.1/openleadkit"
    )
    settings = Settings(database_url=database_url, test_database_url=test_url)
    try:
        safe_url = validate_test_database_urls(settings)
    except DatabaseError as exc:
        pytest.fail(f"Database tests were rejected: {exc}")
    monkeypatch.setenv("DATABASE_URL", safe_url)
    clear_settings_cache()
    alembic = Config("alembic.ini")
    migration_error: str | None = None
    try:
        command.upgrade(alembic, "head")
    except Exception as exc:
        migration_error = type(exc).__name__
    if migration_error:
        pytest.fail(
            f"Could not prepare the test PostgreSQL database ({migration_error})",
            pytrace=False,
        )
    engine = create_engine(safe_url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
        monkeypatch.setenv("DATABASE_URL", database_url)
        clear_settings_cache()

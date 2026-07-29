"""Database engine, sessions, health checks, and migration status."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from openleadkit.config import Settings, get_settings
from openleadkit.exceptions import DatabaseError

REQUIRED_EXTENSIONS = {"citext", "pg_trgm"}
HEAD_REVISION = "0001_initial"


def build_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    return create_engine(url, pool_pre_ping=True, future=True)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    db_engine = engine or build_engine()
    session = session_factory(db_engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@dataclass(frozen=True)
class DatabaseHealth:
    version: str
    database: str
    user: str
    extensions: frozenset[str]
    migration_revision: str | None

    @property
    def missing_extensions(self) -> set[str]:
        return REQUIRED_EXTENSIONS - self.extensions

    @property
    def migrations_current(self) -> bool:
        return self.migration_revision == HEAD_REVISION


def inspect_database(engine: Engine) -> DatabaseHealth:
    try:
        with engine.connect() as connection:
            version, database, user, extension_names = connection.execute(
                text(
                    """
                    SELECT
                        version(),
                        current_database(),
                        current_user,
                        ARRAY(
                            SELECT extname::text
                            FROM pg_extension
                            WHERE extname IN ('citext', 'pg_trgm')
                            ORDER BY extname
                        )
                    """
                )
            ).one()
            revision = MigrationContext.configure(connection).get_current_revision()
    except SQLAlchemyError as exc:
        raise DatabaseError("Could not connect to PostgreSQL") from exc
    return DatabaseHealth(
        version=str(version),
        database=str(database),
        user=str(user),
        extensions=frozenset(str(extension) for extension in extension_names),
        migration_revision=revision,
    )


def validate_test_database_urls(settings: Settings) -> str:
    test_url = settings.test_database_url
    if not test_url:
        raise DatabaseError("TEST_DATABASE_URL is not configured")
    if test_url == settings.database_url:
        raise DatabaseError("TEST_DATABASE_URL cannot equal DATABASE_URL")
    database_name = make_url(test_url).database or ""
    if "test" not in database_name.casefold():
        raise DatabaseError("The test database name must contain the word 'test'")
    return test_url

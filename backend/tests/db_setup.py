"""Test database bootstrap.

IMPORTANT: this module must not import anything from ``app`` at module level.
``tests/conftest.py`` calls :func:`configure_test_database_url` before the first
``app.*`` import, so the global ``settings`` and ``engine`` already point at the
test database.
"""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
TEST_DB_SUFFIX = "_test"


def _source_database_url() -> str:
    """Resolve the app's DATABASE_URL like Settings does: env var first, then ../.env.

    ``dotenv_values`` expands ``${POSTGRES_PASSWORD}`` references, as pydantic-settings does.
    """
    from_env = os.environ.get("DATABASE_URL")
    if from_env:
        return from_env
    from_file = dotenv_values(REPO_ROOT / ".env").get("DATABASE_URL")
    if from_file:
        return from_file
    raise RuntimeError(
        "Cannot derive a test database: set TEST_DATABASE_URL or DATABASE_URL "
        "(environment or the repo-root .env)."
    )


def derive_test_url(url: str) -> URL:
    """Same server and credentials, database name + ``_test`` (unless already suffixed)."""
    parsed = make_url(url)
    if not parsed.database:
        raise RuntimeError("DATABASE_URL has no database name.")
    if parsed.database.endswith(TEST_DB_SUFFIX):
        return parsed
    return parsed.set(database=f"{parsed.database}{TEST_DB_SUFFIX}")


def configure_test_database_url() -> None:
    """Point ``DATABASE_URL`` at the test database. Call before importing ``app``."""
    explicit = os.environ.get("TEST_DATABASE_URL")
    url = make_url(explicit) if explicit else derive_test_url(_source_database_url())
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)


def assert_test_database(engine: Engine) -> None:
    """Refuse to continue unless the engine is connected to a ``*_test`` database."""
    name = engine.url.database
    if not name or not name.endswith(TEST_DB_SUFFIX):
        raise RuntimeError(
            f"Refusing to run: tests must use a database whose name ends with "
            f"'{TEST_DB_SUFFIX}', but the engine points at {name!r}."
        )


def ensure_database_exists(engine: Engine) -> None:
    """Create the engine's database via the ``postgres`` maintenance DB if missing."""
    assert_test_database(engine)
    name = engine.url.database
    assert name is not None
    admin = create_engine(
        engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": name},
            ).scalar()
            if not exists:
                quoted = admin.dialect.identifier_preparer.quote(name)
                conn.execute(text(f"CREATE DATABASE {quoted}"))
    finally:
        admin.dispose()


def migrate_to_head() -> None:
    """Run ``alembic upgrade head``; env.py reads the URL from ``settings.DATABASE_URL``."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "app" / "alembic"))
    command.upgrade(config, "head")

import pytest
from sqlalchemy import create_engine

from app.core.db import engine
from tests.db_setup import assert_test_database, derive_test_url


def test_guard_accepts_test_database() -> None:
    assert_test_database(engine)
    assert engine.url.database is not None
    assert engine.url.database.endswith("_test")


def test_guard_rejects_non_test_database() -> None:
    other = create_engine("postgresql+psycopg://u:p@localhost:5432/app")
    with pytest.raises(RuntimeError, match="_test"):
        assert_test_database(other)


def test_derive_test_url_appends_suffix_once() -> None:
    url = "postgresql://postgres:secret@localhost:5432/app"
    assert derive_test_url(url).database == "app_test"
    assert derive_test_url(str(derive_test_url(url))).database == "app_test"

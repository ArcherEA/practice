from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from tests.db_setup import (
    assert_test_database,
    configure_test_database_url,
    ensure_database_exists,
    migrate_to_head,
)

# Must run before the first `app.*` import: points DATABASE_URL at the *_test database
# so the global `settings` and `engine` never touch the dev database.
configure_test_database_url()

from app.core.config import settings  # noqa: E402
from app.core.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from tests.utils.user import authentication_token_from_email  # noqa: E402
from tests.utils.utils import get_superuser_token_headers  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session]:
    assert_test_database(engine)
    ensure_database_exists(engine)
    migrate_to_head()
    with Session(engine) as session:
        init_db(session)
        yield session
        assert_test_database(engine)
        for table in reversed(SQLModel.metadata.sorted_tables):
            if table.name != "alembic_version":
                session.execute(table.delete())
        session.commit()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )

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

from app import crud  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import engine, init_db  # noqa: E402
from app.core.roles import UserRole  # noqa: E402
from app.core.storage import get_storage  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User, UserCreate  # noqa: E402
from tests.utils.files import Headers, MakeUser  # noqa: E402
from tests.utils.storage import FakeStorage  # noqa: E402
from tests.utils.user import (  # noqa: E402
    authentication_token_from_email,
    user_authentication_headers,
)
from tests.utils.utils import (  # noqa: E402
    get_superuser_token_headers,
    random_email,
    random_lower_string,
)


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


@pytest.fixture
def fake_storage() -> Generator[FakeStorage]:
    """Replaces real S3 storage for the test; the override is removed afterwards."""
    storage = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: storage
    yield storage
    app.dependency_overrides.pop(get_storage, None)


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


@pytest.fixture
def make_user(client: TestClient, db: Session) -> MakeUser:
    """Create a user with the given role and log in: returns `(user, auth_headers)`."""

    def _make(
        role: UserRole = UserRole.member, superuser: bool = False
    ) -> tuple[User, Headers]:
        email, password = random_email(), random_lower_string()
        user = crud.create_user(
            session=db,
            user_create=UserCreate(
                email=email, password=password, role=role, is_superuser=superuser
            ),
        )
        headers = user_authentication_headers(
            client=client, email=email, password=password
        )
        return user, headers

    return _make

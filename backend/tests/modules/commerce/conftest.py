from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.core.roles import UserRole
from app.core.storage import get_storage
from app.main import create_app
from tests.utils.files import Headers, MakeUser
from tests.utils.storage import FakeStorage


@pytest.fixture(scope="module")
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture(scope="module")
def commerce_client(storage: FakeStorage) -> Generator[TestClient]:
    """A client for an app with the commerce module enabled (and a fake bucket)."""
    overrides: dict[str, str] = {"MODULES": "items,commerce"}
    app = create_app(Settings(**overrides))  # type: ignore[arg-type] # str is parsed by the validator
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def store_currencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three currencies, including the zero-decimal yen."""
    monkeypatch.setattr(settings, "STORE_CURRENCIES", ["usd", "eur", "jpy"])
    monkeypatch.setattr(settings, "STORE_DEFAULT_CURRENCY", "usd")
    monkeypatch.setattr(settings, "STORE_TIMEZONE", "Europe/Berlin")


@pytest.fixture
def admin(make_user: MakeUser) -> Headers:
    return make_user(UserRole.admin)[1]

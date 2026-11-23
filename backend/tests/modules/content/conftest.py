from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.storage import get_storage
from app.main import create_app
from tests.utils.storage import FakeStorage


@pytest.fixture(scope="module")
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture(scope="module")
def content_client(storage: FakeStorage) -> Generator[TestClient]:
    """A client for an app with the content module enabled (and a fake bucket)."""
    overrides: dict[str, str] = {"MODULES": "items,content"}
    app = create_app(Settings(**overrides))  # type: ignore[arg-type] # str is parsed by the validator
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as client:
        yield client

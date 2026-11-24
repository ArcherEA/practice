from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import Settings
from app.core.storage import get_storage
from app.main import create_app
from app.models import User
from app.modules.community import events, service
from app.modules.community.events import CommunityEvent
from app.modules.content import service as content_service
from app.modules.content.models import Page, Post
from app.modules.content.schemas import PageCreate, PostCreate
from tests.utils.storage import FakeStorage
from tests.utils.utils import random_lower_string


@pytest.fixture(scope="module")
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture(scope="module")
def cclient(storage: FakeStorage) -> Generator[TestClient]:
    """A client for an app with content + community enabled (and a fake bucket)."""
    overrides: dict[str, str] = {"MODULES": "items,content,community"}
    app = create_app(Settings(**overrides))  # type: ignore[arg-type] # str is parsed by the validator
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as client:
        yield client


class Clock:
    """Moves the community clock without sleeping."""

    def __init__(self) -> None:
        self.offset = timedelta(0)

    def now(self) -> datetime:
        return datetime.now(UTC) + self.offset

    def advance(self, **kwargs: float) -> None:
        self.offset += timedelta(**kwargs)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(service, "now", fake.now)
    return fake


@pytest.fixture
def emitted(monkeypatch: pytest.MonkeyPatch) -> list[CommunityEvent]:
    """Collects the events the service emits (`events.emit` is a no-op by default)."""
    collected: list[CommunityEvent] = []
    monkeypatch.setattr(events, "emit", collected.append)
    return collected


MakePost = Callable[..., Post]
MakePage = Callable[..., Page]


@pytest.fixture
def make_post(
    db: Session, make_user: Callable[..., tuple[User, dict[str, str]]]
) -> MakePost:
    def _make(*, published: bool = True) -> Post:
        author, _ = make_user()
        post = content_service.create_post(
            session=db,
            user=author,
            data=PostCreate(title=f"Post {random_lower_string()[:12]}"),
        )
        if published:
            post = content_service.set_status(session=db, item=post, status="published")
        return post

    return _make


@pytest.fixture
def make_page(
    db: Session, make_user: Callable[..., tuple[User, dict[str, str]]]
) -> MakePage:
    def _make(*, published: bool = True) -> Page:
        author, _ = make_user()
        page = content_service.create_page(
            session=db,
            user=author,
            data=PageCreate(title=f"Page {random_lower_string()[:12]}"),
        )
        if published:
            page = content_service.set_status(session=db, item=page, status="published")
        return page

    return _make

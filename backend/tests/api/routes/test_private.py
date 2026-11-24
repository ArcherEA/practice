import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import crud
from app.core.config import settings
from app.models import User


def test_create_user(client: TestClient, db: Session) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/private/users/",
        json={
            "email": "pollo@listo.com",
            "password": "password123",
            "full_name": "Pollo Listo",
        },
    )

    assert r.status_code == 200

    data = r.json()

    user = db.exec(select(User).where(User.id == data["id"])).first()

    assert user
    assert user.email == "pollo@listo.com"
    assert user.full_name == "Pollo Listo"


def test_create_user_retries_when_username_is_taken_concurrently(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulate a parallel request that took the picked username first: the first
    # pick collides with an existing user, the retry gets a free name.
    taken = db.exec(select(User)).first()
    assert taken
    picks = iter([taken.username, "pollo_retry_ok"])
    monkeypatch.setattr(crud, "generate_username", lambda **_: next(picks))

    r = client.post(
        f"{settings.API_V1_STR}/private/users/",
        json={
            "email": "pollo-retry@listo.com",
            "password": "password123",
            "full_name": "Pollo Retry",
        },
    )

    assert r.status_code == 200
    assert r.json()["username"] == "pollo_retry_ok"

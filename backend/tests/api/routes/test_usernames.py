"""Usernames and bio through signup, admin create, PATCH /users/me and admin update."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.core.roles import UserRole
from app.models import User, UserCreate, get_datetime_utc
from tests.utils.files import MakeUser
from tests.utils.utils import random_email, random_lower_string, random_username

USERS = f"{settings.API_V1_STR}/users"


def signup(client: TestClient, **extra: str) -> dict[str, object]:
    body = {"email": random_email(), "password": random_lower_string(), **extra}
    response = client.post(f"{USERS}/signup", json=body)
    assert response.status_code == 200, response.text
    data: dict[str, object] = response.json()
    return data


def test_signup_without_username_generates_one(client: TestClient) -> None:
    data = signup(client, full_name="Grace Hopper")
    assert str(data["username"]).startswith("grace_hopper")
    other = signup(client, full_name="Grace Hopper")
    assert other["username"] != data["username"]
    assert str(other["username"]).startswith("grace_hopper_")


def test_signup_without_a_name_never_derives_the_username_from_the_email(
    client: TestClient,
) -> None:
    local = random_lower_string()[:10]
    response = client.post(
        f"{USERS}/signup",
        json={"email": f"{local}@example.com", "password": random_lower_string()},
    )
    data = response.json()
    # usernames are public, so no part of the email may leak into them
    assert data["username"] == f"member_{data['id'].replace('-', '')[:8]}"
    assert local not in data["username"]


def test_signup_with_username_normalizes_to_lowercase(client: TestClient) -> None:
    name = random_username()
    data = signup(client, username=name.upper())
    assert data["username"] == name


def test_signup_username_is_unique_case_insensitively(client: TestClient) -> None:
    name = random_username()
    signup(client, username=name)
    response = client.post(
        f"{USERS}/signup",
        json={
            "email": random_email(),
            "password": random_lower_string(),
            "username": name.upper(),
        },
    )
    assert response.status_code == 400
    assert "taken" in response.json()["detail"]


def test_signup_rejects_bad_and_reserved_usernames(client: TestClient) -> None:
    for bad in ("ab", "a" * 31, "has space", "dash-ed", "Admin", "SETTINGS", "null"):
        response = client.post(
            f"{USERS}/signup",
            json={
                "email": random_email(),
                "password": random_lower_string(),
                "username": bad,
            },
        )
        assert response.status_code == 422, bad


def test_admin_create_username_is_optional(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    generated = client.post(
        f"{USERS}/",
        headers=superuser_token_headers,
        json={"email": random_email(), "password": random_lower_string()},
    )
    assert generated.status_code == 200
    assert generated.json()["username"]
    name = random_username()
    chosen = client.post(
        f"{USERS}/",
        headers=superuser_token_headers,
        json={
            "email": random_email(),
            "password": random_lower_string(),
            "username": name,
        },
    )
    assert chosen.json()["username"] == name
    clash = client.post(
        f"{USERS}/",
        headers=superuser_token_headers,
        json={
            "email": random_email(),
            "password": random_lower_string(),
            "username": name,
        },
    )
    assert clash.status_code == 400


def test_crud_generates_a_username_on_clash_and_for_reserved(db: Session) -> None:
    first = crud.create_user(
        session=db, user_create=UserCreate(email=random_email(), password="x" * 8)
    )
    assert first.username
    # the full name "Admin" would be the reserved name `admin`
    reserved = crud.create_user(
        session=db,
        user_create=UserCreate(
            email=random_email(), password="x" * 8, full_name="Admin"
        ),
    )
    assert reserved.username.startswith("admin_")
    assert reserved.username != "admin"


def test_patch_me_changes_the_username_once_per_30_days(
    client: TestClient, db: Session, make_user: MakeUser
) -> None:
    user, headers = make_user()
    old = user.username
    new = random_username()
    response = client.patch(f"{USERS}/me", headers=headers, json={"username": new})
    assert response.status_code == 200, response.text
    assert response.json()["username"] == new
    assert response.json()["username_changed_at"]
    # a second change right away is refused, with the date it will work again
    again = client.patch(
        f"{USERS}/me", headers=headers, json={"username": random_username()}
    )
    assert again.status_code == 400
    can_change = (get_datetime_utc() + timedelta(days=30)).date().isoformat()
    assert can_change in again.json()["detail"]
    # the same name is a no-op, not an error
    same = client.patch(f"{USERS}/me", headers=headers, json={"username": new.upper()})
    assert same.status_code == 200
    assert same.json()["username"] == new
    assert old != new
    # after 30 days it is allowed again
    db_user = db.get(User, user.id)
    assert db_user is not None
    db_user.username_changed_at = get_datetime_utc() - timedelta(days=31)
    db.add(db_user)
    db.commit()
    later = random_username()
    ok = client.patch(f"{USERS}/me", headers=headers, json={"username": later})
    assert ok.status_code == 200
    assert ok.json()["username"] == later


def test_patch_me_username_rules(client: TestClient, make_user: MakeUser) -> None:
    taken, _ = make_user()
    _, headers = make_user()
    clash = client.patch(
        f"{USERS}/me", headers=headers, json={"username": taken.username.upper()}
    )
    assert clash.status_code == 409
    reserved = client.patch(f"{USERS}/me", headers=headers, json={"username": "root"})
    assert reserved.status_code == 422
    # a refused change does not use up the 30 days
    ok = client.patch(
        f"{USERS}/me", headers=headers, json={"username": random_username()}
    )
    assert ok.status_code == 200


def test_patch_me_null_username_keeps_it(
    client: TestClient, make_user: MakeUser
) -> None:
    user, headers = make_user()
    response = client.patch(
        f"{USERS}/me", headers=headers, json={"username": None, "full_name": "Zed"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == user.username


def test_patch_me_bio(client: TestClient, make_user: MakeUser) -> None:
    _, headers = make_user()
    response = client.patch(
        f"{USERS}/me", headers=headers, json={"bio": "  Hello\r\nthere  "}
    )
    assert response.json()["bio"] == "Hello\nthere"
    assert (
        client.patch(
            f"{USERS}/me", headers=headers, json={"bio": "x" * 501}
        ).status_code
        == 422
    )
    assert (
        client.patch(f"{USERS}/me", headers=headers, json={"bio": "a\x00b"}).status_code
        == 422
    )
    cleared = client.patch(f"{USERS}/me", headers=headers, json={"bio": "  "})
    assert cleared.json()["bio"] is None
    me = client.get(f"{USERS}/me", headers=headers).json()
    assert me["bio"] is None
    assert me["username"]


def test_admin_can_change_a_username_without_the_limit(
    client: TestClient, make_user: MakeUser
) -> None:
    admin, admin_headers = make_user(UserRole.admin)
    target, _ = make_user()
    for _ in range(2):
        name = random_username()
        response = client.patch(
            f"{USERS}/{target.id}", headers=admin_headers, json={"username": name}
        )
        assert response.status_code == 200, response.text
        assert response.json()["username"] == name
    clash = client.patch(
        f"{USERS}/{target.id}", headers=admin_headers, json={"username": admin.username}
    )
    assert clash.status_code == 409
    # an explicit null does not wipe the NOT NULL column
    keep = client.patch(
        f"{USERS}/{target.id}", headers=admin_headers, json={"username": None}
    )
    assert keep.status_code == 200
    assert keep.json()["username"] == name


def test_private_route_creates_a_username(client: TestClient) -> None:
    response = client.post(
        f"{settings.API_V1_STR}/private/users/",
        json={
            "email": random_email(),
            "password": "password123",
            "full_name": "Pri Vate",
        },
    )
    assert response.json()["username"].startswith("pri_vate")

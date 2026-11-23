from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.core.roles import UserRole
from app.models import User, UserCreate
from tests.utils.user import user_authentication_headers
from tests.utils.utils import random_email, random_lower_string

USERS = f"{settings.API_V1_STR}/users"


def make_user(
    db: Session,
    client: TestClient,
    role: UserRole = UserRole.member,
    is_superuser: bool = False,
) -> tuple[User, dict[str, str]]:
    email, password = random_email(), random_lower_string()
    user = crud.create_user(
        session=db,
        user_create=UserCreate(
            email=email, password=password, role=role, is_superuser=is_superuser
        ),
    )
    headers = user_authentication_headers(client=client, email=email, password=password)
    return user, headers


def test_me_includes_role(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
) -> None:
    r = client.get(f"{USERS}/me", headers=superuser_token_headers)
    assert r.json()["role"] == "admin"
    r = client.get(f"{USERS}/me", headers=normal_user_token_headers)
    assert r.json()["role"] == "member"


def test_signup_creates_member_even_if_role_sent(client: TestClient) -> None:
    r = client.post(
        f"{USERS}/signup",
        json={
            "email": random_email(),
            "password": random_lower_string(),
            "role": "admin",
            "is_superuser": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["role"] == "member"
    assert r.json()["is_superuser"] is False


def test_update_me_ignores_role(client: TestClient, db: Session) -> None:
    user, headers = make_user(db, client)
    r = client.patch(f"{USERS}/me", headers=headers, json={"role": "admin"})
    assert r.status_code == 200
    assert r.json()["role"] == "member"
    db.refresh(user)
    assert user.role == UserRole.member


def test_admin_can_list_and_read_users(client: TestClient, db: Session) -> None:
    _, admin_h = make_user(db, client, UserRole.admin)
    member, _ = make_user(db, client)
    assert client.get(f"{USERS}/", headers=admin_h).status_code == 200
    r = client.get(f"{USERS}/{member.id}", headers=admin_h)
    assert r.status_code == 200
    assert r.json()["role"] == "member"


def test_admin_can_create_update_delete_members(
    client: TestClient, db: Session
) -> None:
    _, admin_h = make_user(db, client, UserRole.admin)
    r = client.post(
        f"{USERS}/",
        headers=admin_h,
        json={
            "email": random_email(),
            "password": random_lower_string(),
            "role": "editor",
        },
    )
    assert r.status_code == 200
    assert r.json()["role"] == "editor"
    member, _ = make_user(db, client)
    r = client.patch(
        f"{USERS}/{member.id}",
        headers=admin_h,
        json={"role": "moderator", "full_name": "Mo"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "moderator"
    assert client.delete(f"{USERS}/{member.id}", headers=admin_h).status_code == 200


def test_non_admin_roles_cannot_manage_users(client: TestClient, db: Session) -> None:
    member, _ = make_user(db, client)
    for role in (UserRole.editor, UserRole.moderator, UserRole.member):
        _, h = make_user(db, client, role)
        assert client.get(f"{USERS}/", headers=h).status_code == 403
        r = client.post(
            f"{USERS}/",
            headers=h,
            json={"email": random_email(), "password": random_lower_string()},
        )
        assert r.status_code == 403
        assert client.get(f"{USERS}/{member.id}", headers=h).status_code == 403
        r = client.patch(f"{USERS}/{member.id}", headers=h, json={"full_name": "x"})
        assert r.status_code == 403
        assert client.delete(f"{USERS}/{member.id}", headers=h).status_code == 403


def test_admin_cannot_create_admin_or_superuser(
    client: TestClient, db: Session
) -> None:
    _, admin_h = make_user(db, client, UserRole.admin)
    for extra in ({"role": "admin"}, {"is_superuser": True}):
        r = client.post(
            f"{USERS}/",
            headers=admin_h,
            json={"email": random_email(), "password": random_lower_string(), **extra},
        )
        assert r.status_code == 403, extra


def test_admin_cannot_grant_or_revoke_admin(client: TestClient, db: Session) -> None:
    _, admin_h = make_user(db, client, UserRole.admin)
    member, _ = make_user(db, client)
    other_admin, _ = make_user(db, client, UserRole.admin)
    r = client.patch(f"{USERS}/{member.id}", headers=admin_h, json={"role": "admin"})
    assert r.status_code == 403
    r = client.patch(
        f"{USERS}/{other_admin.id}", headers=admin_h, json={"role": "member"}
    )
    assert r.status_code == 403
    db.refresh(member)
    db.refresh(other_admin)
    assert member.role == UserRole.member
    assert other_admin.role == UserRole.admin


def test_admin_cannot_touch_superusers(client: TestClient, db: Session) -> None:
    _, admin_h = make_user(db, client, UserRole.admin)
    boss, _ = make_user(db, client, UserRole.admin, is_superuser=True)
    r = client.patch(f"{USERS}/{boss.id}", headers=admin_h, json={"full_name": "x"})
    assert r.status_code == 403
    assert client.delete(f"{USERS}/{boss.id}", headers=admin_h).status_code == 403
    assert client.get(f"{USERS}/{boss.id}", headers=admin_h).status_code == 200


def test_admin_cannot_set_is_superuser(client: TestClient, db: Session) -> None:
    _, admin_h = make_user(db, client, UserRole.admin)
    member, _ = make_user(db, client)
    r = client.patch(
        f"{USERS}/{member.id}", headers=admin_h, json={"is_superuser": True}
    )
    assert r.status_code == 403
    db.refresh(member)
    assert member.is_superuser is False
    # Sending the unchanged value is not a change.
    r = client.patch(
        f"{USERS}/{member.id}", headers=admin_h, json={"is_superuser": False}
    )
    assert r.status_code == 200


def test_superuser_can_grant_admin_and_superuser(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    member, _ = make_user(db, client)
    r = client.patch(
        f"{USERS}/{member.id}",
        headers=superuser_token_headers,
        json={"role": "admin", "is_superuser": True},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    assert r.json()["is_superuser"] is True
    r = client.post(
        f"{USERS}/",
        headers=superuser_token_headers,
        json={
            "email": random_email(),
            "password": random_lower_string(),
            "role": "admin",
        },
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    # A superuser can delete another superuser.
    r = client.delete(f"{USERS}/{member.id}", headers=superuser_token_headers)
    assert r.status_code == 200


def test_user_cannot_change_own_role_via_admin_endpoint(
    client: TestClient, db: Session
) -> None:
    admin, admin_h = make_user(db, client, UserRole.admin)
    r = client.patch(f"{USERS}/{admin.id}", headers=admin_h, json={"role": "member"})
    assert r.status_code == 403
    assert "own role" in r.json()["detail"]
    # Even unchanged, a non-superuser admin cannot edit an admin (incl. themselves).
    r = client.patch(f"{USERS}/{admin.id}", headers=admin_h, json={"role": "admin"})
    assert r.status_code == 403


def test_admin_cannot_modify_or_delete_admins(client: TestClient, db: Session) -> None:
    admin, admin_h = make_user(db, client, UserRole.admin)
    other, _ = make_user(db, client, UserRole.admin)
    for body in (
        {"full_name": "x"},
        {"email": random_email()},
        {"password": random_lower_string()},
        {"is_active": False},
        {"role": "member"},
    ):
        r = client.patch(f"{USERS}/{other.id}", headers=admin_h, json=body)
        assert r.status_code == 403, body
    r = client.patch(f"{USERS}/{other.id}", headers=admin_h, json={"full_name": "x"})
    assert r.json()["detail"] == "Only superusers can modify admins"
    r = client.delete(f"{USERS}/{other.id}", headers=admin_h)
    assert r.status_code == 403
    assert r.json()["detail"] == "Only superusers can delete admins"
    # Self-service through the admin endpoint is also refused.
    r = client.patch(f"{USERS}/{admin.id}", headers=admin_h, json={"full_name": "me"})
    assert r.status_code == 403
    r = client.patch(f"{USERS}/me", headers=admin_h, json={"full_name": "me"})
    assert r.status_code == 200


def test_superuser_can_modify_and_delete_admins(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    other, _ = make_user(db, client, UserRole.admin)
    r = client.patch(
        f"{USERS}/{other.id}", headers=superuser_token_headers, json={"full_name": "x"}
    )
    assert r.status_code == 200
    r = client.delete(f"{USERS}/{other.id}", headers=superuser_token_headers)
    assert r.status_code == 200


def test_superuser_cannot_change_own_role(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    me = client.get(f"{USERS}/me", headers=superuser_token_headers).json()
    r = client.patch(
        f"{USERS}/{me['id']}", headers=superuser_token_headers, json={"role": "member"}
    )
    assert r.status_code == 403


def test_invalid_role_rejected(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    member, _ = make_user(db, client)
    r = client.patch(
        f"{USERS}/{member.id}", headers=superuser_token_headers, json={"role": "boss"}
    )
    assert r.status_code == 422

import logging
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import files as file_service
from app.core.config import settings
from app.core.roles import UserRole
from app.core.storage import StorageNotConfiguredError
from app.models import File, FileStatus, User, get_datetime_utc
from tests.utils.files import API, Headers, MakeUser, create_upload, upload_ready
from tests.utils.storage import FakeStorage


def key_of(file: dict[str, Any]) -> str:
    return f"{file['owner_id']}/{file['id']}"


def used_bytes(db: Session) -> int:
    db.expire_all()
    return file_service._used_bytes(db)


# ---- create + confirm ----


def test_create_upload_returns_presigned_put(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    user, headers = make_user()
    r = create_upload(client, headers, size=1234)
    assert r.status_code == 200
    body = r.json()
    assert body["upload_method"] == "PUT"
    assert body["upload_headers"] == {"Content-Type": "application/pdf"}
    assert body["expires_in"] == settings.UPLOAD_URL_EXPIRE_SECONDS
    assert body["upload_url"].startswith("https://bucket.test/")
    assert body["file"]["status"] == "pending"
    assert body["file"]["size"] == 1234
    assert body["file"]["owner_id"] == str(user.id)


@pytest.mark.parametrize(
    "payload",
    [
        {"content_type": "not a mime"},
        {"content_type": "text/html; charset=utf-8"},
        {"content_type": "nosubtype"},
        {"size": 0},
        {"filename": ""},
        {"filename": "bad\x00name"},
    ],
)
def test_create_upload_validates_input(
    client: TestClient,
    make_user: MakeUser,
    fake_storage: FakeStorage,
    payload: dict[str, Any],
) -> None:
    _, headers = make_user()
    body = {
        "filename": "a.pdf",
        "content_type": "application/pdf",
        "size": 10,
        **payload,
    }
    assert client.post(f"{API}/files/", headers=headers, json=body).status_code == 422


def test_create_upload_requires_auth(client: TestClient) -> None:
    r = client.post(f"{API}/files/", json={})
    assert r.status_code == 401


def test_create_upload_over_max_size(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, headers = make_user()
    r = create_upload(client, headers, size=settings.UPLOAD_MAX_BYTES + 1)
    assert r.status_code == 413
    assert "too large" in r.json()["detail"]


def test_public_only_for_inline_images(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, headers = make_user()
    assert create_upload(client, headers, public=True).status_code == 400
    ok = create_upload(client, headers, public=True, content_type="image/png")
    assert ok.status_code == 200
    assert ok.json()["file"]["public"] is True


def test_confirm_marks_ready_and_is_idempotent(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, headers = make_user()
    file = upload_ready(client, fake_storage, headers)
    assert file["status"] == "ready"
    again = client.post(f"{API}/files/{file['id']}/confirm", headers=headers)
    assert again.status_code == 200


def test_confirm_missing_object_deletes_row(
    client: TestClient, make_user: MakeUser, db: Session, fake_storage: FakeStorage
) -> None:
    _, headers = make_user()
    file = create_upload(client, headers).json()["file"]
    r = client.post(f"{API}/files/{file['id']}/confirm", headers=headers)
    assert r.status_code == 400
    db.expire_all()
    assert db.get(File, uuid.UUID(file["id"])) is None


@pytest.mark.parametrize("real_size", [999, 1001, 5_000_000_000])
def test_confirm_wrong_size_deletes_object_and_row(
    client: TestClient,
    make_user: MakeUser,
    db: Session,
    fake_storage: FakeStorage,
    real_size: int,
) -> None:
    _, headers = make_user()
    file = create_upload(client, headers, size=1000).json()["file"]
    fake_storage.simulate_upload(key_of(file), real_size)
    r = client.post(f"{API}/files/{file['id']}/confirm", headers=headers)
    assert r.status_code == 400
    assert key_of(file) not in fake_storage.objects
    db.expire_all()
    assert db.get(File, uuid.UUID(file["id"])) is None


def test_confirm_over_max_even_if_size_matches(
    client: TestClient,
    make_user: MakeUser,
    db: Session,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = make_user()
    file = create_upload(client, headers, size=1000).json()["file"]
    fake_storage.simulate_upload(key_of(file), 1000)
    monkeypatch.setattr(settings, "UPLOAD_MAX_BYTES", 500)
    r = client.post(f"{API}/files/{file['id']}/confirm", headers=headers)
    assert r.status_code == 400
    assert "too large" in r.json()["detail"]


def test_confirm_other_users_file_is_404(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, owner = make_user()
    _, other = make_user()
    file = create_upload(client, owner).json()["file"]
    r = client.post(f"{API}/files/{file['id']}/confirm", headers=other)
    assert r.status_code == 404


# ---- list, download, delete ----


def test_list_shows_only_my_ready_files(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, headers = make_user()
    _, other = make_user()
    ready = upload_ready(client, fake_storage, headers)
    create_upload(client, headers)  # stays pending
    upload_ready(client, fake_storage, other)
    r = client.get(f"{API}/files/", headers=headers)
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert [f["id"] for f in r.json()["data"]] == [ready["id"]]


def test_download_url_inline_only_for_safe_images(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, headers = make_user()
    img = upload_ready(client, fake_storage, headers, content_type="image/png")
    svg = upload_ready(
        client, fake_storage, headers, content_type="image/svg+xml", filename="a b.svg"
    )
    html = upload_ready(client, fake_storage, headers, content_type="text/html")
    img_url = client.get(f"{API}/files/{img['id']}/download", headers=headers).json()
    assert "disposition=inline" in img_url["url"]
    assert img_url["expires_in"] == settings.DOWNLOAD_URL_EXPIRE_SECONDS
    svg_url = client.get(f"{API}/files/{svg['id']}/download", headers=headers).json()
    assert "attachment; filename*=UTF-8''a%20b.svg" in svg_url["url"]
    html_url = client.get(f"{API}/files/{html['id']}/download", headers=headers).json()
    assert "attachment" in html_url["url"]


def test_download_pending_is_409_and_foreign_is_404(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, headers = make_user()
    _, other = make_user()
    pending = create_upload(client, headers).json()["file"]
    assert (
        client.get(f"{API}/files/{pending['id']}/download", headers=headers).status_code
        == 409
    )
    assert (
        client.get(f"{API}/files/{pending['id']}/download", headers=other).status_code
        == 404
    )
    missing = client.get(f"{API}/files/{uuid.uuid4()}/download", headers=headers)
    assert missing.status_code == 404


def test_admin_can_download_and_delete_foreign_file(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, owner = make_user()
    _, admin = make_user(role=UserRole.admin)
    file = upload_ready(client, fake_storage, owner)
    assert (
        client.get(f"{API}/files/{file['id']}/download", headers=admin).status_code
        == 200
    )
    assert client.delete(f"{API}/files/{file['id']}", headers=admin).status_code == 200


def test_admin_cannot_touch_files_of_admins_or_superusers(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, admin = make_user(role=UserRole.admin)
    _, other_admin = make_user(role=UserRole.admin)
    _, superuser = make_user(superuser=True)
    for owner in (other_admin, superuser):
        file = upload_ready(client, fake_storage, owner)
        url = f"{API}/files/{file['id']}"
        assert client.get(f"{url}/download", headers=admin).status_code == 404
        assert client.delete(url, headers=admin).status_code == 404
        assert key_of(file) in fake_storage.objects


def test_superuser_can_touch_files_of_admins(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, other_admin = make_user(role=UserRole.admin)
    _, superuser = make_user(superuser=True)
    file = upload_ready(client, fake_storage, other_admin)
    url = f"{API}/files/{file['id']}"
    assert client.get(f"{url}/download", headers=superuser).status_code == 200
    assert client.delete(url, headers=superuser).status_code == 200


def test_delete_removes_row_and_object(
    client: TestClient, make_user: MakeUser, db: Session, fake_storage: FakeStorage
) -> None:
    _, headers = make_user()
    _, other = make_user()
    file = upload_ready(client, fake_storage, headers)
    assert client.delete(f"{API}/files/{file['id']}", headers=other).status_code == 404
    assert key_of(file) in fake_storage.objects
    assert (
        client.delete(f"{API}/files/{file['id']}", headers=headers).status_code == 200
    )
    assert key_of(file) not in fake_storage.objects
    db.expire_all()
    assert db.get(File, uuid.UUID(file["id"])) is None


def test_delete_survives_storage_failure(
    client: TestClient, make_user: MakeUser, db: Session, fake_storage: FakeStorage
) -> None:
    _, headers = make_user()
    file = upload_ready(client, fake_storage, headers)
    fake_storage.fail_delete = True
    assert (
        client.delete(f"{API}/files/{file['id']}", headers=headers).status_code == 200
    )
    db.expire_all()
    assert db.get(File, uuid.UUID(file["id"])) is None


# ---- usage limits ----


def test_user_quota_returns_413(
    client: TestClient,
    make_user: MakeUser,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "STORAGE_USER_QUOTA_BYTES", 2500)
    _, headers = make_user()
    assert create_upload(client, headers, size=1000).status_code == 200
    assert (
        create_upload(client, headers, size=1000).status_code == 200
    )  # pending counts
    r = create_upload(client, headers, size=1000)
    assert r.status_code == 413
    assert r.json()["detail"] == "Your storage quota is full"
    # another user is unaffected
    _, other = make_user()
    assert create_upload(client, other, size=1000).status_code == 200


def test_user_quota_frees_up_after_delete(
    client: TestClient,
    make_user: MakeUser,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "STORAGE_USER_QUOTA_BYTES", 1500)
    _, headers = make_user()
    file = upload_ready(client, fake_storage, headers)
    assert create_upload(client, headers).status_code == 413
    client.delete(f"{API}/files/{file['id']}", headers=headers)
    assert create_upload(client, headers).status_code == 200


def test_total_limit_returns_507(
    client: TestClient,
    make_user: MakeUser,
    db: Session,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = make_user()
    monkeypatch.setattr(settings, "STORAGE_TOTAL_LIMIT_BYTES", used_bytes(db) + 1500)
    assert create_upload(client, headers, size=1000).status_code == 200  # reserved
    r = create_upload(client, headers, size=1000)
    assert r.status_code == 507
    assert r.json()["detail"] == "Storage is full"
    # a different user hits the same global limit
    _, other = make_user()
    assert create_upload(client, other, size=1000).status_code == 507


def test_daily_limit_returns_429(
    client: TestClient,
    make_user: MakeUser,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "UPLOADS_PER_USER_PER_DAY", 2)
    _, headers = make_user()
    assert create_upload(client, headers, size=10).status_code == 200
    assert create_upload(client, headers, size=10).status_code == 200
    r = create_upload(client, headers, size=10)
    assert r.status_code == 429
    _, other = make_user()
    assert create_upload(client, other, size=10).status_code == 200


def test_daily_limit_ignores_rows_older_than_a_day(
    client: TestClient,
    make_user: MakeUser,
    db: Session,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "UPLOADS_PER_USER_PER_DAY", 1)
    user, headers = make_user()
    old = File(
        owner_id=user.id,
        key=f"{user.id}/old",
        filename="old",
        content_type="text/plain",
        size=1,
        status=FileStatus.ready,
        created_at=get_datetime_utc() - timedelta(hours=25),
    )
    db.add(old)
    db.commit()
    assert create_upload(client, headers, size=10).status_code == 200
    assert create_upload(client, headers, size=10).status_code == 429


def test_superuser_is_exempt_from_quota_and_daily_limit(
    client: TestClient,
    make_user: MakeUser,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "STORAGE_USER_QUOTA_BYTES", 100)
    monkeypatch.setattr(settings, "UPLOADS_PER_USER_PER_DAY", 1)
    _, su = make_user(superuser=True)
    for _ in range(3):
        assert create_upload(client, su, size=1000).status_code == 200
    # a normal user with the same limits is blocked
    _, member = make_user()
    assert create_upload(client, member, size=1000).status_code == 413


def test_superuser_is_not_exempt_from_total_limit(
    client: TestClient,
    make_user: MakeUser,
    db: Session,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, su = make_user(superuser=True)
    monkeypatch.setattr(settings, "STORAGE_TOTAL_LIMIT_BYTES", used_bytes(db) + 500)
    assert create_upload(client, su, size=1000).status_code == 507


# ---- usage endpoint ----


def test_usage_requires_admin(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, member = make_user()
    _, editor = make_user(role=UserRole.editor)
    assert client.get(f"{API}/files/usage", headers=member).status_code == 403
    assert client.get(f"{API}/files/usage", headers=editor).status_code == 403


@pytest.mark.parametrize("kind", ["admin", "superuser"])
def test_usage_report(
    client: TestClient,
    make_user: MakeUser,
    db: Session,
    fake_storage: FakeStorage,
    kind: str,
) -> None:
    _, headers = make_user(
        role=UserRole.admin if kind == "admin" else UserRole.member,
        superuser=kind == "superuser",
    )
    upload_ready(client, fake_storage, headers, size=7777)
    r = client.get(f"{API}/files/usage", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["limit_bytes"] == settings.STORAGE_TOTAL_LIMIT_BYTES
    assert body["total_bytes"] == used_bytes(db)
    assert body["file_count"] >= 1
    assert body["top_users"]
    sizes = [u["total_bytes"] for u in body["top_users"]]
    assert sizes == sorted(sizes, reverse=True)
    assert {"user_id", "email", "total_bytes", "file_count"} <= body["top_users"][
        0
    ].keys()


# ---- avatars ----


def test_set_avatar_and_replace_deletes_old_file(
    client: TestClient, make_user: MakeUser, db: Session, fake_storage: FakeStorage
) -> None:
    user, headers = make_user()
    first = upload_ready(client, fake_storage, headers, content_type="image/png")
    r = client.put(
        f"{API}/users/me/avatar", headers=headers, json={"file_id": first["id"]}
    )
    assert r.status_code == 200
    assert "disposition=inline" in r.json()["avatar_url"]
    assert client.get(f"{API}/users/me", headers=headers).json()["avatar_url"]

    second = upload_ready(client, fake_storage, headers, content_type="image/webp")
    r = client.put(
        f"{API}/users/me/avatar", headers=headers, json={"file_id": second["id"]}
    )
    assert r.status_code == 200
    assert key_of(first) not in fake_storage.objects
    assert key_of(second) in fake_storage.objects
    db.expire_all()
    assert db.get(File, uuid.UUID(first["id"])) is None
    assert db.get(User, user.id).avatar_file_id == uuid.UUID(second["id"])  # type: ignore[union-attr]  # user exists

    # setting the same file again changes nothing
    r = client.put(
        f"{API}/users/me/avatar", headers=headers, json={"file_id": second["id"]}
    )
    assert r.status_code == 200
    assert key_of(second) in fake_storage.objects


def test_avatar_must_be_ready_owned_image(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, headers = make_user()
    _, other = make_user()
    pdf = upload_ready(client, fake_storage, headers)
    svg = upload_ready(client, fake_storage, headers, content_type="image/svg+xml")
    pending = create_upload(client, headers, content_type="image/png").json()["file"]
    foreign = upload_ready(client, fake_storage, other, content_type="image/png")

    def put(file_id: str) -> int:
        r = client.put(
            f"{API}/users/me/avatar", headers=headers, json={"file_id": file_id}
        )
        return int(r.status_code)

    assert put(pdf["id"]) == 400
    assert put(svg["id"]) == 400
    assert put(pending["id"]) == 400
    assert put(foreign["id"]) == 404
    assert put(str(uuid.uuid4())) == 404


def test_delete_avatar(
    client: TestClient, make_user: MakeUser, db: Session, fake_storage: FakeStorage
) -> None:
    _, headers = make_user()
    file = upload_ready(client, fake_storage, headers, content_type="image/gif")
    client.put(f"{API}/users/me/avatar", headers=headers, json={"file_id": file["id"]})
    r = client.delete(f"{API}/users/me/avatar", headers=headers)
    assert r.status_code == 200
    assert r.json()["avatar_url"] is None
    assert key_of(file) not in fake_storage.objects
    # deleting again is a no-op
    assert client.delete(f"{API}/users/me/avatar", headers=headers).status_code == 200


def test_deleting_avatar_file_directly_clears_the_avatar(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, headers = make_user()
    file = upload_ready(client, fake_storage, headers, content_type="image/png")
    client.put(f"{API}/users/me/avatar", headers=headers, json={"file_id": file["id"]})
    assert (
        client.delete(f"{API}/files/{file['id']}", headers=headers).status_code == 200
    )
    assert client.get(f"{API}/users/me", headers=headers).json()["avatar_url"] is None


def test_public_avatar_uses_public_base_url(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    fake_storage.public_base_url = "https://cdn.test"
    _, headers = make_user()
    file = upload_ready(
        client, fake_storage, headers, content_type="image/png", public=True
    )
    r = client.put(
        f"{API}/users/me/avatar", headers=headers, json={"file_id": file["id"]}
    )
    assert r.json()["avatar_url"] == f"https://cdn.test/{key_of(file)}"
    # private avatars stay signed even when a public base URL is configured
    private = upload_ready(client, fake_storage, headers, content_type="image/png")
    r = client.put(
        f"{API}/users/me/avatar", headers=headers, json={"file_id": private["id"]}
    )
    assert "bucket.test" in r.json()["avatar_url"]


def test_avatar_url_in_user_lists_and_lookups(
    client: TestClient,
    make_user: MakeUser,
    superuser_token_headers: Headers,
    fake_storage: FakeStorage,
) -> None:
    user, headers = make_user()
    file = upload_ready(client, fake_storage, headers, content_type="image/png")
    client.put(f"{API}/users/me/avatar", headers=headers, json={"file_id": file["id"]})
    r = client.get(f"{API}/users/?limit=500", headers=superuser_token_headers)
    mine = next(u for u in r.json()["data"] if u["id"] == str(user.id))
    assert mine["avatar_url"]
    assert client.get(f"{API}/users/{user.id}", headers=headers).json()["avatar_url"]
    assert client.get(f"{API}/users/{user.id}", headers=superuser_token_headers).json()[
        "avatar_url"
    ]
    patched = client.patch(
        f"{API}/users/{user.id}",
        headers=superuser_token_headers,
        json={"full_name": "N"},
    )
    assert patched.json()["avatar_url"]
    me = client.patch(f"{API}/users/me", headers=headers, json={"full_name": "M"})
    assert me.json()["avatar_url"]
    assert client.post(f"{API}/login/test-token", headers=headers).json()["avatar_url"]


# ---- deleting users removes their objects ----


def test_admin_deleting_user_deletes_their_objects(
    client: TestClient,
    make_user: MakeUser,
    db: Session,
    superuser_token_headers: Headers,
    fake_storage: FakeStorage,
) -> None:
    user, headers = make_user()
    user_id = user.id
    avatar = upload_ready(client, fake_storage, headers, content_type="image/png")
    other = upload_ready(client, fake_storage, headers)
    client.put(
        f"{API}/users/me/avatar", headers=headers, json={"file_id": avatar["id"]}
    )
    r = client.delete(f"{API}/users/{user_id}", headers=superuser_token_headers)
    assert r.status_code == 200
    assert not fake_storage.objects.keys() & {key_of(avatar), key_of(other)}
    db.expire_all()
    assert db.exec(select(File).where(File.owner_id == user_id)).all() == []


def test_deleting_own_account_deletes_objects_and_tolerates_failures(
    client: TestClient,
    make_user: MakeUser,
    fake_storage: FakeStorage,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Alembic (run by the session fixture) disables pre-existing loggers; re-enable ours.
    logging.getLogger("app.core.storage").disabled = False
    _, headers = make_user()
    file = upload_ready(client, fake_storage, headers)
    fake_storage.fail_delete = True
    r = client.delete(f"{API}/users/me", headers=headers)
    assert r.status_code == 200
    assert "Could not delete storage object" in caplog.text
    assert key_of(file) in fake_storage.objects  # leaked, but logged

    _, headers2 = make_user()
    file2 = upload_ready(client, fake_storage, headers2)
    fake_storage.fail_delete = False
    assert client.delete(f"{API}/users/me", headers=headers2).status_code == 200
    assert key_of(file2) not in fake_storage.objects


# ---- cleanup ----


def test_cleanup_removes_only_stale_pending_files(
    client: TestClient, make_user: MakeUser, db: Session, fake_storage: FakeStorage
) -> None:
    user, headers = make_user()
    stale = create_upload(client, headers).json()["file"]
    fresh = create_upload(client, headers).json()["file"]
    ready = upload_ready(client, fake_storage, headers)
    for f in (stale, ready):
        row = db.get(File, uuid.UUID(f["id"]))
        assert row is not None
        row.created_at = get_datetime_utc() - timedelta(hours=30)
        db.add(row)
    db.commit()
    fake_storage.simulate_upload(key_of(stale), 1000)

    removed = file_service.cleanup_stale_pending(session=db, storage=fake_storage)
    assert removed >= 1
    db.expire_all()
    assert db.get(File, uuid.UUID(stale["id"])) is None
    assert key_of(stale) not in fake_storage.objects
    assert db.get(File, uuid.UUID(fresh["id"])) is not None
    assert db.get(File, uuid.UUID(ready["id"])) is not None
    assert user.id  # silence unused


def test_cleanup_script_main_runs(
    db: Session, fake_storage: FakeStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.scripts import cleanup_files

    monkeypatch.setattr(cleanup_files, "get_storage", lambda: fake_storage)
    assert cleanup_files.main() >= 0


# ---- storage not configured ----


def test_unconfigured_storage_returns_503(
    client: TestClient, make_user: MakeUser
) -> None:
    from app.api.routes import files as files_routes  # noqa: F401
    from app.core.storage import S3Storage, get_storage
    from app.main import app

    unconfigured = S3Storage(
        settings.model_copy(update={"S3_ENDPOINT_URL": None, "S3_BUCKET": None})
    )
    app.dependency_overrides[get_storage] = lambda: unconfigured
    try:
        _, headers = make_user()
        assert create_upload(client, headers).status_code == 503
        # the reservation is rolled back, so it does not eat quota
        assert client.get(f"{API}/files/", headers=headers).json()["count"] == 0
        # users without an avatar are unaffected
        assert client.get(f"{API}/users/me", headers=headers).status_code == 200
    finally:
        app.dependency_overrides.pop(get_storage, None)


def test_unconfigured_storage_raises_on_use() -> None:
    from app.core.storage import S3Storage

    storage = S3Storage(settings.model_copy(update={"S3_ENDPOINT_URL": None}))
    with pytest.raises(StorageNotConfiguredError):
        storage.head("k")
    with pytest.raises(StorageNotConfiguredError):
        storage.presign_upload("k", content_type="a/b", size=1, expires_in=60)
    no_bucket = S3Storage(
        settings.model_copy(update={"S3_ENDPOINT_URL": "http://x", "S3_BUCKET": None})
    )
    with pytest.raises(StorageNotConfiguredError):
        no_bucket.presign_download("k", filename="f", content_type="a/b", expires_in=1)


def test_confirm_and_download_with_unconfigured_storage_are_503(
    client: TestClient, make_user: MakeUser, db: Session
) -> None:
    from app.core.storage import S3Storage, get_storage
    from app.main import app

    user, headers = make_user()
    pending = File(
        owner_id=user.id, key=f"{user.id}/p", filename="p", content_type="a/b", size=1
    )
    ready = File(
        owner_id=user.id,
        key=f"{user.id}/r",
        filename="r",
        content_type="a/b",
        size=1,
        status=FileStatus.ready,
    )
    db.add(pending)
    db.add(ready)
    db.commit()
    unconfigured = S3Storage(settings.model_copy(update={"S3_ENDPOINT_URL": None}))
    app.dependency_overrides[get_storage] = lambda: unconfigured
    try:
        assert (
            client.post(
                f"{API}/files/{pending.id}/confirm", headers=headers
            ).status_code
            == 503
        )
        assert (
            client.get(f"{API}/files/{ready.id}/download", headers=headers).status_code
            == 503
        )
    finally:
        app.dependency_overrides.pop(get_storage, None)


def test_avatar_url_is_none_when_storage_unconfigured(
    client: TestClient, make_user: MakeUser, db: Session
) -> None:
    from app.core.storage import S3Storage, get_storage
    from app.main import app

    user, headers = make_user()
    file = File(
        owner_id=user.id,
        key=f"{user.id}/a",
        filename="a.png",
        content_type="image/png",
        size=1,
        status=FileStatus.ready,
    )
    db.add(file)
    db.commit()
    user.avatar_file_id = file.id
    db.add(user)
    db.commit()
    unconfigured = S3Storage(settings.model_copy(update={"S3_ENDPOINT_URL": None}))
    app.dependency_overrides[get_storage] = lambda: unconfigured
    try:
        r = client.get(f"{API}/users/me", headers=headers)
        assert r.status_code == 200
        assert r.json()["avatar_url"] is None
    finally:
        app.dependency_overrides.pop(get_storage, None)


# ---- pure helpers ----


def test_s3_storage_presigns_locally_with_public_endpoint() -> None:
    from app.core.storage import S3Storage

    storage = S3Storage(
        settings.model_copy(
            update={
                "S3_ENDPOINT_URL": "http://storage:8333",
                "S3_PUBLIC_ENDPOINT_URL": "http://localhost:9000",
                "S3_BUCKET": "b",
                "S3_ACCESS_KEY_ID": "k",
                "S3_SECRET_ACCESS_KEY": "s",
                "S3_PUBLIC_BASE_URL": "https://cdn.test/",
            }
        )
    )
    up = storage.presign_upload("u/1", content_type="image/png", size=42, expires_in=60)
    assert up.url.startswith("http://localhost:9000/b/u/1?")
    assert "content-length" in up.url and "content-type" in up.url  # signed headers
    assert "StorageClass" not in up.url and "storage-class" not in up.url
    assert up.headers == {"Content-Type": "image/png"}
    down = storage.presign_download(
        "u/1", filename="é x.pdf", content_type="application/pdf", expires_in=60
    )
    assert down.startswith("http://localhost:9000/b/u/1?")
    assert "response-content-disposition=attachment" in down
    assert "UTF-8%27%27%25C3%25A9%2520x.pdf" in down
    inline = storage.presign_download(
        "u/1", filename="a.png", content_type="IMAGE/PNG", expires_in=60
    )
    assert "response-content-disposition=inline" in inline
    assert storage.public_url("u/a b") == "https://cdn.test/u/a%20b"
    assert (
        S3Storage(settings.model_copy(update={"S3_PUBLIC_BASE_URL": None})).public_url(
            "k"
        )
        is None
    )


# ---- stable public image URL: GET /files/{id}/content ----


def test_content_redirects_public_image_to_public_url(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    fake_storage.public_base_url = "https://cdn.test"
    _, headers = make_user()
    file = upload_ready(
        client, fake_storage, headers, content_type="image/png", public=True
    )
    r = client.get(f"{API}/files/{file['id']}/content", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == f"https://cdn.test/{key_of(file)}"


def test_content_redirects_to_fresh_signed_url_without_public_base(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage
) -> None:
    _, headers = make_user()
    file = upload_ready(
        client, fake_storage, headers, content_type="image/webp", public=True
    )
    r = client.get(f"{API}/files/{file['id']}/content", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith(f"https://bucket.test/{key_of(file)}?")
    assert "disposition=inline" in r.headers["location"]


def test_content_needs_no_auth_but_hides_private_pending_and_unknown(
    client: TestClient, make_user: MakeUser, fake_storage: FakeStorage, db: Session
) -> None:
    _, headers = make_user()
    private = upload_ready(client, fake_storage, headers, content_type="image/png")
    assert client.get(f"{API}/files/{private['id']}/content").status_code == 404
    # even the owner gets 404 here: the endpoint only serves public files
    assert (
        client.get(f"{API}/files/{private['id']}/content", headers=headers).status_code
        == 404
    )
    pending = create_upload(
        client, headers, content_type="image/png", filename="p.png", public=True
    ).json()["file"]
    assert client.get(f"{API}/files/{pending['id']}/content").status_code == 404
    assert client.get(f"{API}/files/{uuid.uuid4()}/content").status_code == 404
    # a non-image file is never served, even if flagged public in the database
    pdf = upload_ready(client, fake_storage, headers)
    row = db.get(File, uuid.UUID(pdf["id"]))
    assert row is not None
    row.public = True
    db.add(row)
    db.commit()
    assert client.get(f"{API}/files/{pdf['id']}/content").status_code == 404


def test_content_503_when_storage_not_configured(
    client: TestClient,
    make_user: MakeUser,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = make_user()
    file = upload_ready(
        client, fake_storage, headers, content_type="image/png", public=True
    )

    def unconfigured(*args: object, **kwargs: object) -> str:
        raise StorageNotConfiguredError("File storage is not configured")

    monkeypatch.setattr(fake_storage, "presign_download", unconfigured)
    r = client.get(f"{API}/files/{file['id']}/content", follow_redirects=False)
    assert r.status_code == 503

"""Product file uploads and protection, store settings validation, money helpers."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlmodel import Session

from app.core.config import Settings, settings
from app.core.roles import UserRole
from app.models import File
from app.modules.commerce import money
from tests.modules.commerce.helpers import (
    ADMIN,
    make_product,
    make_variant,
    ok,
    sku,
    upload_product_file,
)
from tests.utils.files import Headers, MakeUser, create_upload
from tests.utils.storage import FakeStorage

FILES = f"{settings.API_V1_STR}/files"
USERS = f"{settings.API_V1_STR}/users"


def test_product_files_may_exceed_the_member_cap(
    commerce_client: TestClient,
    admin: Headers,
    storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_MAX_BYTES", 1000)
    monkeypatch.setattr(settings, "PRODUCT_FILE_MAX_BYTES", 5000)
    # the normal flow keeps its cap...
    assert create_upload(commerce_client, admin, size=2000).status_code == 413
    # ...the commerce flow has the larger one
    big = upload_product_file(commerce_client, storage, admin, size=2000)
    assert big["size"] == 2000 and big["status"] == "ready"
    too_big = commerce_client.post(
        f"{ADMIN}/files",
        headers=admin,
        json={"filename": "x.zip", "content_type": "application/zip", "size": 5001},
    )
    assert too_big.status_code == 413 and "5000" in too_big.text


def test_confirm_checks_the_product_cap_and_real_size(
    commerce_client: TestClient,
    admin: Headers,
    storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PRODUCT_FILE_MAX_BYTES", 5000)
    ticket = ok(
        commerce_client.post(
            f"{ADMIN}/files",
            headers=admin,
            json={"filename": "x.zip", "content_type": "application/zip", "size": 100},
        )
    )["file"]
    key = f"{ticket['owner_id']}/{ticket['id']}"
    storage.simulate_upload(key, 9000)  # the browser sent something else
    response = commerce_client.post(
        f"{ADMIN}/files/{ticket['id']}/confirm", headers=admin
    )
    assert response.status_code == 400
    assert key in storage.deleted
    missing = commerce_client.post(
        f"{ADMIN}/files/{ticket['id']}/confirm", headers=admin
    )
    assert missing.status_code == 404  # the row was removed


def test_generic_confirm_still_enforces_the_member_cap(
    commerce_client: TestClient,
    admin: Headers,
    storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_MAX_BYTES", 1000)
    ticket = ok(
        commerce_client.post(
            f"{ADMIN}/files",
            headers=admin,
            json={"filename": "x.zip", "content_type": "application/zip", "size": 900},
        )
    )["file"]
    storage.simulate_upload(f"{ticket['owner_id']}/{ticket['id']}", 900)
    assert (
        commerce_client.post(
            f"{FILES}/{ticket['id']}/confirm", headers=admin
        ).status_code
        == 200
    )


def test_product_uploads_are_private_and_skip_user_quotas(
    commerce_client: TestClient,
    admin: Headers,
    make_user: MakeUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "STORAGE_USER_QUOTA_BYTES", 10)
    monkeypatch.setattr(settings, "UPLOADS_PER_USER_PER_DAY", 0)
    ticket = ok(
        commerce_client.post(
            f"{ADMIN}/files",
            headers=admin,
            json={
                "filename": "a.png",
                "content_type": "image/png",
                "size": 500,
                "public": True,
            },
        )
    )
    assert ticket["file"]["public"] is False  # the flag is ignored
    # a regular upload by the same admin is still limited
    assert create_upload(commerce_client, admin, size=500).status_code in (413, 429)
    # the global limit applies to product files too
    monkeypatch.setattr(settings, "STORAGE_TOTAL_LIMIT_BYTES", 1)
    full = commerce_client.post(
        f"{ADMIN}/files",
        headers=admin,
        json={"filename": "b.pdf", "content_type": "application/pdf", "size": 5},
    )
    assert full.status_code == 507


def test_someone_elses_file_cannot_be_confirmed_here(
    commerce_client: TestClient, admin: Headers, make_user: MakeUser
) -> None:
    ticket = ok(
        commerce_client.post(
            f"{ADMIN}/files",
            headers=admin,
            json={"filename": "a.pdf", "content_type": "application/pdf", "size": 5},
        )
    )["file"]
    other_admin = make_user(UserRole.admin)[1]
    assert (
        commerce_client.post(
            f"{ADMIN}/files/{ticket['id']}/confirm", headers=other_admin
        ).status_code
        == 404
    )


def test_file_in_use_cannot_be_deleted_through_the_files_api(
    commerce_client: TestClient, admin: Headers, storage: FakeStorage
) -> None:
    file = upload_product_file(commerce_client, storage, admin)
    product = make_product(commerce_client, admin, "digital")
    variant = make_variant(commerce_client, admin, product["id"], file_id=file["id"])
    response = commerce_client.delete(f"{FILES}/{file['id']}", headers=admin)
    assert response.status_code == 409 and "in use" in response.text
    ok(commerce_client.delete(f"{ADMIN}/variants/{variant['id']}", headers=admin))
    # released together with the variant, so the file is gone
    assert (
        commerce_client.delete(f"{FILES}/{file['id']}", headers=admin).status_code
        == 404
    )


def test_admin_who_owns_product_files_cannot_be_deleted(
    commerce_client: TestClient,
    storage: FakeStorage,
    make_user: MakeUser,
    superuser_token_headers: Headers,
    db: Session,
) -> None:
    owner, owner_headers = make_user(UserRole.admin)
    file = upload_product_file(commerce_client, storage, owner_headers)
    product = make_product(commerce_client, owner_headers, "digital")
    variant = make_variant(
        commerce_client, owner_headers, product["id"], file_id=file["id"]
    )

    # a superuser deleting the admin is refused with a clear message...
    response = commerce_client.delete(
        f"{USERS}/{owner.id}", headers=superuser_token_headers
    )
    assert response.status_code == 409
    assert "in use" in response.text
    # ...and so is the admin deleting themselves
    mine = commerce_client.delete(f"{USERS}/me", headers=owner_headers)
    assert mine.status_code == 409
    # nothing was removed
    db.expire_all()
    assert db.get(File, file["id"]) is not None
    assert f"{file['owner_id']}/{file['id']}" not in storage.deleted

    # once the file is no longer used, the deletion works and cleans up the object
    ok(
        commerce_client.delete(
            f"{ADMIN}/variants/{variant['id']}", headers=owner_headers
        )
    )
    ok(commerce_client.delete(f"{USERS}/{owner.id}", headers=superuser_token_headers))


def test_users_without_product_files_are_deleted_as_before(
    commerce_client: TestClient,
    make_user: MakeUser,
    superuser_token_headers: Headers,
) -> None:
    member, _ = make_user(UserRole.member)
    ok(commerce_client.delete(f"{USERS}/{member.id}", headers=superuser_token_headers))


# --- settings ---


def make_settings(**env: str) -> Settings:
    return Settings(**env)  # type: ignore[arg-type] # strings are parsed by the validators


def test_store_defaults() -> None:
    parsed = make_settings(STORE_CURRENCIES="usd")
    assert parsed.STORE_CURRENCIES == ["usd"]
    assert parsed.STORE_DEFAULT_CURRENCY == "usd"
    assert parsed.STORE_TIMEZONE == "UTC"
    assert parsed.PRODUCT_FILE_MAX_BYTES == 100 * 1024**2


def test_default_currency_is_the_first_of_the_list() -> None:
    parsed = make_settings(STORE_CURRENCIES=" eur , usd,eur ")
    assert parsed.STORE_CURRENCIES == ["eur", "usd"]
    assert parsed.STORE_DEFAULT_CURRENCY == "eur"
    explicit = make_settings(STORE_CURRENCIES="eur,usd", STORE_DEFAULT_CURRENCY="usd")
    assert explicit.STORE_DEFAULT_CURRENCY == "usd"


@pytest.mark.parametrize(
    ("env", "fragment"),
    [
        (
            {"STORE_CURRENCIES": "usd,eur", "STORE_DEFAULT_CURRENCY": "gbp"},
            "must be one of",
        ),
        ({"STORE_CURRENCIES": "USD"}, "lower-case"),
        ({"STORE_CURRENCIES": "dollars"}, "Invalid currency"),
        ({"STORE_CURRENCIES": "us"}, "Invalid currency"),
        ({"STORE_CURRENCIES": " , "}, "at least one"),
        ({"STORE_TIMEZONE": "Mars/Base"}, "STORE_TIMEZONE"),
        ({"PRODUCT_FILE_MAX_BYTES": "0"}, "positive"),
    ],
)
def test_invalid_store_settings_fail_at_startup(
    env: dict[str, str], fragment: str
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        make_settings(**env)
    assert fragment in str(exc_info.value)


def test_valid_timezone_is_accepted() -> None:
    assert make_settings(STORE_TIMEZONE="Asia/Tokyo").STORE_TIMEZONE == "Asia/Tokyo"


# --- money ---


def test_exponents() -> None:
    assert money.exponent("usd") == 2
    assert money.exponent("JPY") == 0
    assert money.exponent("krw") == 0
    assert money.exponent("kwd") == 3
    assert money.exponent("eur") == 2


def test_to_decimal_and_format() -> None:
    assert money.to_decimal(1999, "usd") == Decimal("19.99")
    assert money.to_decimal(1500, "jpy") == Decimal(1500)
    assert money.to_decimal(1234, "kwd") == Decimal("1.234")
    assert money.format_amount(1999, "usd") == "19.99 USD"
    assert money.format_amount(123456789, "eur") == "1,234,567.89 EUR"
    assert money.format_amount(1500, "jpy") == "1,500 JPY"
    assert money.format_amount(5, "usd") == "0.05 USD"


def test_allowed_currencies_follow_settings() -> None:
    assert money.allowed_currencies() == ["usd", "eur", "jpy"]
    assert money.default_currency() == "usd"
    assert money.is_allowed(" EUR ") and not money.is_allowed("gbp")
    assert sku()

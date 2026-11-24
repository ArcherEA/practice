"""Runs against the real local storage server (compose `storage`); skipped when it is not reachable.

Start it with: docker compose up -d --wait storage storage-init
"""

import uuid
from collections.abc import Generator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.storage import S3Storage
from tests.utils.user import authentication_token_from_email


def _reachable() -> bool:
    if not (
        settings.S3_ENDPOINT_URL and settings.S3_BUCKET and settings.S3_ACCESS_KEY_ID
    ):
        return False
    try:
        # Raises when the server is down or the bucket is missing.
        S3Storage(settings)._client.head_bucket(Bucket=settings.S3_BUCKET)
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _reachable(), reason="S3 storage server is not reachable"
)


@pytest.fixture
def storage() -> S3Storage:
    return S3Storage(settings)


@pytest.fixture
def key(storage: S3Storage) -> Generator[str]:
    k = f"integration-tests/{uuid.uuid4()}"
    yield k
    storage.delete(k)


def test_put_with_declared_size_and_type_succeeds_and_head_sees_it(
    storage: S3Storage, key: str
) -> None:
    up = storage.presign_upload(
        key, content_type="application/pdf", size=1000, expires_in=60
    )
    r = httpx.put(up.url, content=b"x" * 1000, headers=up.headers)
    assert r.status_code == 200, r.text
    info = storage.head(key)
    assert info is not None
    assert info.size == 1000


@pytest.mark.parametrize("body_size", [999, 1001, 20_000])
def test_put_with_wrong_size_is_rejected_by_the_bucket(
    storage: S3Storage, key: str, body_size: int
) -> None:
    up = storage.presign_upload(
        key, content_type="application/pdf", size=1000, expires_in=60
    )
    r = httpx.put(up.url, content=b"x" * body_size, headers=up.headers)
    assert r.status_code == 403
    assert storage.head(key) is None


def test_put_with_wrong_content_type_is_rejected(storage: S3Storage, key: str) -> None:
    up = storage.presign_upload(
        key, content_type="application/pdf", size=10, expires_in=60
    )
    r = httpx.put(up.url, content=b"x" * 10, headers={"Content-Type": "text/html"})
    assert r.status_code == 403
    assert storage.head(key) is None


def test_head_missing_returns_none_and_delete_removes(
    storage: S3Storage, key: str
) -> None:
    assert storage.head(key) is None
    up = storage.presign_upload(key, content_type="text/plain", size=3, expires_in=60)
    assert httpx.put(up.url, content=b"abc", headers=up.headers).status_code == 200
    storage.delete(key)
    assert storage.head(key) is None


def test_presigned_get_forces_download_for_non_images(
    storage: S3Storage, key: str
) -> None:
    up = storage.presign_upload(key, content_type="text/html", size=5, expires_in=60)
    httpx.put(up.url, content=b"<b>x<", headers=up.headers).raise_for_status()
    url = storage.presign_download(
        key, filename="é x.html", content_type="text/html", expires_in=60
    )
    r = httpx.get(url)
    assert r.status_code == 200
    assert (
        r.headers["content-disposition"]
        == "attachment; filename*=UTF-8''%C3%A9%20x.html"
    )
    assert r.content == b"<b>x<"


def test_presigned_get_serves_images_inline(storage: S3Storage, key: str) -> None:
    up = storage.presign_upload(key, content_type="image/png", size=4, expires_in=60)
    httpx.put(up.url, content=b"\x89PNG", headers=up.headers).raise_for_status()
    url = storage.presign_download(
        key, filename="a.png", content_type="image/png", expires_in=60
    )
    r = httpx.get(url)
    assert r.headers["content-disposition"] == "inline"
    assert r.headers["content-type"] == "image/png"


def test_presigned_get_returns_cache_control(storage: S3Storage, key: str) -> None:
    up = storage.presign_upload(key, content_type="image/png", size=4, expires_in=60)
    httpx.put(up.url, content=b"\x89PNG", headers=up.headers).raise_for_status()
    private = httpx.get(
        storage.presign_download(
            key, filename="a.png", content_type="image/png", expires_in=60
        )
    )
    assert private.headers["cache-control"] == "private, max-age=60, immutable"
    public = httpx.get(
        storage.presign_download(
            key, filename="a.png", content_type="image/png", expires_in=60, public=True
        )
    )
    assert public.headers["cache-control"] == "public, max-age=60, immutable"


def test_bucket_cors_allows_the_frontend_origin(storage: S3Storage, key: str) -> None:
    up = storage.presign_upload(key, content_type="image/png", size=4, expires_in=60)
    r = httpx.options(
        up.url,
        headers={
            "Origin": settings.FRONTEND_HOST,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == settings.FRONTEND_HOST
    assert "PUT" in r.headers["access-control-allow-methods"]


def test_full_flow_through_the_api_with_real_storage(
    client: TestClient, db: Session
) -> None:
    """create -> PUT to the bucket -> confirm -> download -> delete, no fakes."""
    headers = authentication_token_from_email(
        client=client,
        email=f"{uuid.uuid4().hex}@example.com",
        db=db,
    )
    api = settings.API_V1_STR
    ticket = client.post(
        f"{api}/files/",
        headers=headers,
        json={"filename": "n.txt", "content_type": "text/plain", "size": 11},
    ).json()
    file_id = ticket["file"]["id"]

    # Wrong size: the bucket itself refuses.
    bad = httpx.put(
        ticket["upload_url"], content=b"too long body", headers=ticket["upload_headers"]
    )
    assert bad.status_code == 403
    assert (
        client.post(f"{api}/files/{file_id}/confirm", headers=headers).status_code
        == 400
    )

    ticket = client.post(
        f"{api}/files/",
        headers=headers,
        json={"filename": "n.txt", "content_type": "text/plain", "size": 11},
    ).json()
    file_id = ticket["file"]["id"]
    good = httpx.put(
        ticket["upload_url"], content=b"hello world", headers=ticket["upload_headers"]
    )
    assert good.status_code == 200
    confirmed = client.post(f"{api}/files/{file_id}/confirm", headers=headers)
    assert confirmed.json()["status"] == "ready"

    url = client.get(f"{api}/files/{file_id}/download", headers=headers).json()["url"]
    got = httpx.get(url)
    assert got.content == b"hello world"
    assert got.headers["content-disposition"].startswith("attachment")

    assert client.delete(f"{api}/files/{file_id}", headers=headers).status_code == 200
    assert httpx.get(url).status_code == 404

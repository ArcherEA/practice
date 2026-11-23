"""Shared helpers for tests that need users with roles and uploaded files."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import settings
from app.models import User
from tests.utils.storage import FakeStorage

API = settings.API_V1_STR
Headers = dict[str, str]
MakeUser = Callable[..., tuple[User, Headers]]


def create_upload(
    client: TestClient,
    headers: Headers,
    *,
    size: int = 1000,
    content_type: str = "application/pdf",
    filename: str = "doc.pdf",
    public: bool = False,
) -> Any:
    return client.post(
        f"{API}/files/",
        headers=headers,
        json={
            "filename": filename,
            "content_type": content_type,
            "size": size,
            "public": public,
        },
    )


def upload_ready(
    client: TestClient, storage: FakeStorage, headers: Headers, **kwargs: Any
) -> dict[str, Any]:
    """Create + simulate the browser upload + confirm. Returns the file JSON."""
    ticket = create_upload(client, headers, **kwargs)
    assert ticket.status_code == 200, ticket.text
    file = ticket.json()["file"]
    size = kwargs.get("size", 1000)
    storage.simulate_upload(f"{file['owner_id']}/{file['id']}", size)
    r = client.post(f"{API}/files/{file['id']}/confirm", headers=headers)
    assert r.status_code == 200, r.text
    result: dict[str, Any] = r.json()
    return result

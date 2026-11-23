"""Small request helpers shared by the community tests."""

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.files import Headers

BASE = f"{settings.API_V1_STR}/community"
MOD = f"{BASE}/moderation"


def add_comment(
    client: TestClient,
    headers: Headers,
    target_id: uuid.UUID,
    *,
    body: str = "A thoughtful comment",
    parent_id: str | None = None,
    kind: str = "posts",
) -> dict[str, Any]:
    payload: dict[str, Any] = {"body": body}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    response = client.post(
        f"{BASE}/{kind}/{target_id}/comments", headers=headers, json=payload
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def list_comments(
    client: TestClient,
    target_id: uuid.UUID,
    headers: Headers | None = None,
    *,
    kind: str = "posts",
    **params: Any,
) -> dict[str, Any]:
    response = client.get(
        f"{BASE}/{kind}/{target_id}/comments", headers=headers, params=params
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def queue(client: TestClient, headers: Headers, **params: Any) -> list[dict[str, Any]]:
    response = client.get(f"{MOD}/comments", headers=headers, params=params)
    assert response.status_code == 200, response.text
    data: list[dict[str, Any]] = response.json()["data"]
    return data


def report(
    client: TestClient,
    headers: Headers,
    comment_id: str,
    reason: str = "spam",
) -> Any:
    return client.post(
        f"{BASE}/comments/{comment_id}/report",
        headers=headers,
        json={"reason": reason},
    )

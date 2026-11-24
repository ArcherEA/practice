"""Small helpers shared by the commerce tests."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.files import Headers, upload_ready
from tests.utils.storage import FakeStorage
from tests.utils.utils import random_lower_string

BASE = f"{settings.API_V1_STR}/commerce"
ADMIN = f"{BASE}/admin"


def unique(prefix: str = "Thing") -> str:
    return f"{prefix} {random_lower_string()[:10]}"


def sku() -> str:
    return f"SKU-{random_lower_string()[:8].upper()}"


def doc(text: str = "hello") -> dict[str, Any]:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def make_product(
    client: TestClient, headers: Headers, type_: str = "physical", **fields: Any
) -> dict[str, Any]:
    payload = {"type": type_, "title": unique("Product"), **fields}
    result: dict[str, Any] = ok(
        client.post(f"{ADMIN}/products", headers=headers, json=payload)
    )
    return result


def make_variant(
    client: TestClient,
    headers: Headers,
    product_id: str,
    **fields: Any,
) -> dict[str, Any]:
    payload = {"sku": sku(), **fields}
    result: dict[str, Any] = ok(
        client.post(
            f"{ADMIN}/products/{product_id}/variants", headers=headers, json=payload
        )
    )
    return result


def set_price(
    client: TestClient,
    headers: Headers,
    variant_id: str,
    currency: str = "usd",
    amount: int = 1000,
) -> Any:
    return client.put(
        f"{ADMIN}/variants/{variant_id}/prices/{currency}",
        headers=headers,
        json={"amount": amount},
    )


def upload_image(
    client: TestClient, storage: FakeStorage, headers: Headers, *, public: bool = True
) -> dict[str, Any]:
    return upload_ready(
        client,
        storage,
        headers,
        content_type="image/png",
        filename="pic.png",
        public=public,
    )


def upload_product_file(
    client: TestClient,
    storage: FakeStorage,
    headers: Headers,
    *,
    size: int = 2000,
    filename: str = "book.pdf",
) -> dict[str, Any]:
    """Upload through the commerce flow (admin only, bigger cap, always private)."""
    ticket = ok(
        client.post(
            f"{ADMIN}/files",
            headers=headers,
            json={
                "filename": filename,
                "content_type": "application/pdf",
                "size": size,
            },
        )
    )
    file = ticket["file"]
    storage.simulate_upload(f"{file['owner_id']}/{file['id']}", size)
    confirmed: dict[str, Any] = ok(
        client.post(f"{ADMIN}/files/{file['id']}/confirm", headers=headers)
    )
    return confirmed


def sellable_product(
    client: TestClient,
    headers: Headers,
    *,
    type_: str = "physical",
    stock: int | None = 5,
    amount: int = 1999,
    publish: bool = True,
    **fields: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A product with one priced variant (usd), published by default."""
    product = make_product(client, headers, type_, **fields)
    variant = make_variant(
        client, headers, product["id"], stock=stock if type_ == "physical" else None
    )
    ok(set_price(client, headers, variant["id"], "usd", amount))
    if publish:
        ok(client.post(f"{ADMIN}/products/{product['id']}/publish", headers=headers))
    return product, variant


def future(hours: int = 48) -> datetime:
    return datetime.now(UTC) + timedelta(hours=hours)


def new_id() -> str:
    return str(uuid.uuid4())

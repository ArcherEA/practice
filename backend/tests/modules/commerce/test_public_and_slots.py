"""Public catalog, slots, currencies and module switch."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.modules.commerce.helpers import (
    ADMIN,
    BASE,
    future,
    make_product,
    make_variant,
    ok,
    sellable_product,
    set_price,
    sku,
    unique,
    upload_image,
)
from tests.utils.files import Headers
from tests.utils.storage import FakeStorage


def test_config_lists_currencies_with_exponent(commerce_client: TestClient) -> None:
    config = ok(commerce_client.get(f"{BASE}/config"))
    assert config["default_currency"] == "usd"
    assert config["timezone"] == "Europe/Berlin"
    assert config["currencies"] == [
        {"code": "usd", "exponent": 2},
        {"code": "eur", "exponent": 2},
        {"code": "jpy", "exponent": 0},
    ]


def test_drafts_and_archived_are_invisible(
    commerce_client: TestClient, admin: Headers
) -> None:
    draft = make_product(commerce_client, admin)
    published, _ = sellable_product(commerce_client, admin)
    archived, _ = sellable_product(commerce_client, admin)
    ok(
        commerce_client.post(
            f"{ADMIN}/products/{archived['id']}/archive", headers=admin
        )
    )
    listing = ok(commerce_client.get(f"{BASE}/products", params={"limit": 100}))
    ids = {p["id"] for p in listing["data"]}
    assert published["id"] in ids
    assert draft["id"] not in ids and archived["id"] not in ids
    for product in (draft, archived):
        assert (
            commerce_client.get(f"{BASE}/products/{product['slug']}").status_code == 404
        )
    assert (
        commerce_client.get(f"{BASE}/products/{published['slug']}").status_code == 200
    )
    # unpublishing hides it again
    ok(
        commerce_client.post(
            f"{ADMIN}/products/{published['id']}/unpublish", headers=admin
        )
    )
    assert (
        commerce_client.get(f"{BASE}/products/{published['slug']}").status_code == 404
    )


def test_public_list_filters_and_paging(
    commerce_client: TestClient, admin: Headers
) -> None:
    category = ok(
        commerce_client.post(
            f"{ADMIN}/categories", headers=admin, json={"name": unique("Shelf")}
        )
    )
    empty = ok(
        commerce_client.post(
            f"{ADMIN}/categories", headers=admin, json={"name": unique("Empty")}
        )
    )
    mine = [
        sellable_product(commerce_client, admin, category_id=category["id"])[0]
        for _ in range(3)
    ]
    sellable_product(commerce_client, admin)  # another category
    result = ok(
        commerce_client.get(
            f"{BASE}/products", params={"category": category["slug"], "limit": 2}
        )
    )
    assert result["count"] == 3 and len(result["data"]) == 2
    assert result["data"][0]["category"]["slug"] == category["slug"]
    rest = ok(
        commerce_client.get(
            f"{BASE}/products",
            params={"category": category["slug"], "skip": 2, "limit": 2},
        )
    )
    assert len(rest["data"]) == 1
    seen = {p["id"] for p in result["data"]} | {p["id"] for p in rest["data"]}
    assert seen == {p["id"] for p in mine}
    digital_only = ok(
        commerce_client.get(
            f"{BASE}/products",
            params={"category": category["slug"], "type": "digital"},
        )
    )
    assert digital_only["count"] == 0
    categories = ok(commerce_client.get(f"{BASE}/categories"))
    slugs = {c["slug"] for c in categories["data"]}
    assert category["slug"] in slugs and empty["slug"] not in slugs
    assert (
        commerce_client.get(f"{BASE}/products", params={"type": "bogus"}).status_code
        == 422
    )
    assert (
        commerce_client.get(f"{BASE}/products", params={"limit": 0}).status_code == 422
    )


def test_currency_selection_and_unavailable_variants(
    commerce_client: TestClient, admin: Headers
) -> None:
    product, variant = sellable_product(commerce_client, admin, amount=1999)
    ok(set_price(commerce_client, admin, variant["id"], "jpy", 2500))
    default = ok(commerce_client.get(f"{BASE}/products/{product['slug']}"))
    assert default["currency"] == "usd"
    assert default["variants"][0]["price"] == 1999
    assert default["variants"][0]["available"] is True
    yen = ok(commerce_client.get(f"{BASE}/products/{product['slug']}?currency=JPY"))
    assert yen["variants"][0]["price"] == 2500 and yen["currency"] == "jpy"
    euro = ok(commerce_client.get(f"{BASE}/products/{product['slug']}?currency=eur"))
    offer = euro["variants"][0]
    assert offer["price"] is None and offer["available"] is False
    assert offer["in_stock"] is True  # in stock, but not sold in euro
    listing = ok(
        commerce_client.get(
            f"{BASE}/products", params={"currency": "eur", "limit": 100}
        )
    )
    row = next(p for p in listing["data"] if p["id"] == product["id"])
    assert row["from_price"] is None and row["available"] is False
    assert row["currency"] == "eur"
    listing = ok(
        commerce_client.get(
            f"{BASE}/products", params={"currency": "jpy", "limit": 100}
        )
    )
    row = next(p for p in listing["data"] if p["id"] == product["id"])
    assert row["from_price"] == 2500 and row["available"] is True
    for path in (f"/products/{product['slug']}", "/products"):
        response = commerce_client.get(f"{BASE}{path}", params={"currency": "gbp"})
        assert response.status_code == 422 and "Allowed" in response.text


def test_from_price_is_the_cheapest_sellable_variant(
    commerce_client: TestClient, admin: Headers
) -> None:
    product = make_product(commerce_client, admin)
    ok(
        commerce_client.post(
            f"{ADMIN}/products/{product['id']}/options",
            headers=admin,
            json={"name": "Size", "values": ["S", "M", "L"]},
        )
    )
    cheap_sold_out = make_variant(
        commerce_client, admin, product["id"], option_values={"Size": "S"}, stock=0
    )
    mid = make_variant(
        commerce_client, admin, product["id"], option_values={"Size": "M"}, stock=4
    )
    big = make_variant(
        commerce_client, admin, product["id"], option_values={"Size": "L"}, stock=9
    )
    for variant, amount in ((cheap_sold_out, 500), (mid, 1500), (big, 2500)):
        ok(set_price(commerce_client, admin, variant["id"], "usd", amount))
    ok(commerce_client.post(f"{ADMIN}/products/{product['id']}/publish", headers=admin))
    detail = ok(commerce_client.get(f"{BASE}/products/{product['slug']}"))
    by_size = {v["option_values"]["Size"]: v for v in detail["variants"]}
    assert by_size["S"]["in_stock"] is False and by_size["S"]["available"] is False
    assert by_size["M"]["stock"] == 4 and by_size["L"]["available"] is True
    assert detail["options"] == [{"name": "Size", "values": ["S", "M", "L"]}]
    listing = ok(commerce_client.get(f"{BASE}/products", params={"limit": 100}))
    row = next(p for p in listing["data"] if p["id"] == product["id"])
    assert row["from_price"] == 1500
    # inactive variants disappear from the public product
    ok(
        commerce_client.patch(
            f"{ADMIN}/variants/{big['id']}", headers=admin, json={"is_active": False}
        )
    )
    detail = ok(commerce_client.get(f"{BASE}/products/{product['slug']}"))
    assert {v["option_values"]["Size"] for v in detail["variants"]} == {"S", "M"}


def test_stock_is_only_shown_for_physical_products(
    commerce_client: TestClient, admin: Headers
) -> None:
    physical, _ = sellable_product(commerce_client, admin, stock=7)
    service = make_product(commerce_client, admin, "service")
    variant = make_variant(commerce_client, admin, service["id"], stock=3)
    ok(set_price(commerce_client, admin, variant["id"]))
    ok(commerce_client.post(f"{ADMIN}/products/{service['id']}/publish", headers=admin))
    assert (
        ok(commerce_client.get(f"{BASE}/products/{physical['slug']}"))["variants"][0][
            "stock"
        ]
        == 7
    )
    assert (
        ok(commerce_client.get(f"{BASE}/products/{service['slug']}"))["variants"][0][
            "stock"
        ]
        is None
    )


def test_product_images_use_the_stable_public_url(
    commerce_client: TestClient, admin: Headers, storage: FakeStorage
) -> None:
    first = upload_image(commerce_client, storage, admin)
    second = upload_image(commerce_client, storage, admin)
    product, _ = sellable_product(
        commerce_client, admin, image_file_ids=[second["id"], first["id"]]
    )
    detail = ok(commerce_client.get(f"{BASE}/products/{product['slug']}"))
    assert detail["image_urls"] == [
        f"/api/v1/files/{second['id']}/content",
        f"/api/v1/files/{first['id']}/content",
    ]
    listing = ok(commerce_client.get(f"{BASE}/products", params={"limit": 100}))
    row = next(p for p in listing["data"] if p["id"] == product["id"])
    assert row["image_url"] == f"/api/v1/files/{second['id']}/content"
    assert (
        commerce_client.get(detail["image_urls"][0], follow_redirects=False).status_code
        == 302
    )
    # a deleted image file just disappears from the product
    ok(commerce_client.delete(f"/api/v1/files/{second['id']}", headers=admin))
    detail = ok(commerce_client.get(f"{BASE}/products/{product['slug']}"))
    assert detail["image_urls"] == [f"/api/v1/files/{first['id']}/content"]


def test_slot_validation(commerce_client: TestClient, admin: Headers) -> None:
    service = make_product(commerce_client, admin, "service")
    url = f"{ADMIN}/products/{service['id']}/slots"
    start = future(48)
    end = start + timedelta(hours=1)
    iso = lambda dt: dt.isoformat()  # noqa: E731

    def post(**fields: object) -> TestClient:
        payload = {
            "starts_at": iso(start),
            "ends_at": iso(end),
            "capacity": 2,
            **fields,
        }
        return commerce_client.post(url, headers=admin, json=payload)  # type: ignore[return-value]

    assert post(ends_at=iso(start)).status_code == 422  # end == start
    assert post(ends_at=iso(start - timedelta(hours=1))).status_code == 422
    assert post(capacity=0).status_code == 422
    naive = post(starts_at=start.replace(tzinfo=None).isoformat())
    assert naive.status_code == 422 and "timezone" in naive.text
    slot = ok(post())
    assert slot["capacity"] == 2 and slot["is_active"] is True
    duplicate = post(capacity=5)
    assert duplicate.status_code == 422 and "same start and end" in duplicate.text
    # the same instant written in another UTC offset is still the same slot
    berlin = start.astimezone(UTC).astimezone(datetime.now().astimezone().tzinfo)
    assert post(starts_at=berlin.isoformat()).status_code == 422
    # a different end is a different slot
    assert post(ends_at=iso(end + timedelta(hours=1))).status_code == 200

    # update: same rules
    other = ok(
        post(
            starts_at=iso(start + timedelta(days=1)),
            ends_at=iso(end + timedelta(days=1)),
        )
    )
    clash = commerce_client.patch(
        f"{ADMIN}/slots/{other['id']}",
        headers=admin,
        json={"starts_at": iso(start), "ends_at": iso(end)},
    )
    assert clash.status_code == 422
    bad = commerce_client.patch(
        f"{ADMIN}/slots/{other['id']}",
        headers=admin,
        json={"ends_at": iso(start - timedelta(days=5))},
    )
    assert bad.status_code == 422
    updated = ok(
        commerce_client.patch(
            f"{ADMIN}/slots/{other['id']}",
            headers=admin,
            json={"capacity": 9, "is_active": False},
        )
    )
    assert updated["capacity"] == 9 and updated["is_active"] is False
    listing = ok(commerce_client.get(url, headers=admin))
    assert listing["count"] == 3
    starts = [s["starts_at"] for s in listing["data"]]
    assert starts == sorted(starts)
    ok(commerce_client.delete(f"{ADMIN}/slots/{other['id']}", headers=admin))
    assert (
        commerce_client.delete(
            f"{ADMIN}/slots/{other['id']}", headers=admin
        ).status_code
        == 404
    )


def test_only_service_products_have_slots(
    commerce_client: TestClient, admin: Headers
) -> None:
    physical = make_product(commerce_client, admin, "physical")
    response = commerce_client.post(
        f"{ADMIN}/products/{physical['id']}/slots",
        headers=admin,
        json={
            "starts_at": future().isoformat(),
            "ends_at": future(49).isoformat(),
            "capacity": 1,
        },
    )
    assert response.status_code == 422


def test_public_slots_are_upcoming_active_and_show_remaining(
    commerce_client: TestClient, admin: Headers
) -> None:
    service = make_product(commerce_client, admin, "service")
    variant = make_variant(commerce_client, admin, service["id"])
    ok(set_price(commerce_client, admin, variant["id"], "usd", 5000))
    ok(commerce_client.post(f"{ADMIN}/products/{service['id']}/publish", headers=admin))

    # Without upcoming slots the service is listed but not available.
    detail = ok(commerce_client.get(f"{BASE}/products/{service['slug']}"))
    assert detail["slots"] == [] and detail["variants"][0]["available"] is False
    assert detail["store_timezone"] == "Europe/Berlin"

    def add(
        start: datetime, capacity: int = 3, active: bool = True
    ) -> dict[str, object]:
        result: dict[str, object] = ok(
            commerce_client.post(
                f"{ADMIN}/products/{service['id']}/slots",
                headers=admin,
                json={
                    "starts_at": start.isoformat(),
                    "ends_at": (start + timedelta(hours=1)).isoformat(),
                    "capacity": capacity,
                    "is_active": active,
                },
            )
        )
        return result

    past = add(datetime.now(UTC) - timedelta(days=1))
    hidden = add(future(72), active=False)
    later = add(future(96), capacity=4)
    soon = add(future(24), capacity=2)
    detail = ok(commerce_client.get(f"{BASE}/products/{service['slug']}"))
    ids = [s["id"] for s in detail["slots"]]
    assert ids == [soon["id"], later["id"]]  # soonest first; past and inactive hidden
    assert past["id"] not in ids and hidden["id"] not in ids
    assert [(s["capacity"], s["remaining"]) for s in detail["slots"]] == [
        (2, 2),
        (4, 4),
    ]
    assert detail["variants"][0]["available"] is True
    listing = ok(commerce_client.get(f"{BASE}/products", params={"limit": 100}))
    row = next(p for p in listing["data"] if p["id"] == service["id"])
    assert row["available"] is True and row["from_price"] == 5000


def test_module_off_means_404(
    commerce_client: TestClient, admin: Headers, superuser_token_headers: Headers
) -> None:
    from app.core.config import Settings, settings
    from app.main import create_app

    overrides: dict[str, str] = {"MODULES": "items"}
    app = create_app(Settings(**overrides))  # type: ignore[arg-type] # str is parsed by the validator
    with TestClient(app) as client:
        for path in (
            "/commerce/config",
            "/commerce/products",
            "/commerce/products/some-slug",
            "/commerce/categories",
            "/commerce/admin/products",
            "/commerce/admin/categories",
        ):
            response = client.get(
                f"{settings.API_V1_STR}{path}", headers=superuser_token_headers
            )
            assert response.status_code == 404, path
        config = client.get(f"{settings.API_V1_STR}/utils/config").json()
    assert "commerce" not in config["modules"]
    assert not any("/commerce" in path for path in app.openapi()["paths"])
    on = ok(commerce_client.get(f"{settings.API_V1_STR}/utils/config"))
    assert "commerce" in on["modules"]
    assert sku()  # keeps the helper import used


def test_stock_zero_marks_the_product_unavailable(
    commerce_client: TestClient, admin: Headers
) -> None:
    product, variant = sellable_product(commerce_client, admin, stock=1)
    ok(
        commerce_client.patch(
            f"{ADMIN}/variants/{variant['id']}", headers=admin, json={"stock": 0}
        )
    )
    detail = ok(commerce_client.get(f"{BASE}/products/{product['slug']}"))
    assert detail["variants"][0]["in_stock"] is False
    listing = ok(commerce_client.get(f"{BASE}/products", params={"limit": 100}))
    row = next(p for p in listing["data"] if p["id"] == product["id"])
    assert row["available"] is False and row["from_price"] is None

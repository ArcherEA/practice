"""Admin API: roles, categories, products, options, variants, prices, publishing."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.roles import UserRole
from tests.modules.commerce.helpers import (
    ADMIN,
    doc,
    make_product,
    make_variant,
    ok,
    sellable_product,
    set_price,
    sku,
    unique,
    upload_image,
    upload_product_file,
)
from tests.utils.files import Headers, MakeUser
from tests.utils.storage import FakeStorage

ZERO = "00000000-0000-0000-0000-000000000000"

ADMIN_ENDPOINTS = [
    ("get", "/categories"),
    ("post", "/categories"),
    ("get", "/products"),
    ("post", "/products"),
    ("get", f"/products/{ZERO}"),
    ("post", f"/products/{ZERO}/publish"),
    ("post", f"/products/{ZERO}/options"),
    ("post", f"/products/{ZERO}/variants"),
    ("get", f"/products/{ZERO}/slots"),
    ("post", f"/products/{ZERO}/slots"),
    ("patch", f"/variants/{ZERO}"),
    ("put", f"/variants/{ZERO}/prices/usd"),
    ("post", "/files"),
    ("post", f"/files/{ZERO}/confirm"),
]


@pytest.mark.parametrize("role", ["member", "editor", "moderator"])
def test_admin_api_forbidden_below_admin(
    commerce_client: TestClient, make_user: MakeUser, role: str
) -> None:
    _, headers = make_user(UserRole(role))
    for method, path in ADMIN_ENDPOINTS:
        response = commerce_client.request(
            method, f"{ADMIN}{path}", headers=headers, json={}
        )
        assert response.status_code == 403, (method, path)


def test_admin_api_needs_login(commerce_client: TestClient) -> None:
    for method, path in ADMIN_ENDPOINTS:
        response = commerce_client.request(method, f"{ADMIN}{path}", json={})
        assert response.status_code == 401, (method, path)


def test_admin_and_superuser_pass(
    commerce_client: TestClient, make_user: MakeUser, superuser_token_headers: Headers
) -> None:
    _, headers = make_user(UserRole.member, superuser=True)
    for who in (superuser_token_headers, headers, make_user(UserRole.admin)[1]):
        assert commerce_client.get(f"{ADMIN}/products", headers=who).status_code == 200


def test_category_crud_and_slugs(commerce_client: TestClient, admin: Headers) -> None:
    name = unique("Books")
    first = ok(
        commerce_client.post(
            f"{ADMIN}/categories", headers=admin, json={"name": name, "position": 2}
        )
    )
    second = ok(
        commerce_client.post(f"{ADMIN}/categories", headers=admin, json={"name": name})
    )
    assert second["slug"] == f"{first['slug']}-2"
    updated = ok(
        commerce_client.patch(
            f"{ADMIN}/categories/{first['id']}",
            headers=admin,
            json={"name": "Renamed", "position": 9},
        )
    )
    assert (updated["name"], updated["position"], updated["slug"]) == (
        "Renamed",
        9,
        first["slug"],
    )
    listing = ok(commerce_client.get(f"{ADMIN}/categories", headers=admin))
    assert listing["count"] >= 2

    # Deleting a category keeps its products.
    product = make_product(commerce_client, admin, category_id=first["id"])
    assert product["category_id"] == first["id"]
    ok(commerce_client.delete(f"{ADMIN}/categories/{first['id']}", headers=admin))
    again = ok(commerce_client.get(f"{ADMIN}/products/{product['id']}", headers=admin))
    assert again["category_id"] is None
    assert (
        commerce_client.delete(
            f"{ADMIN}/categories/{first['id']}", headers=admin
        ).status_code
        == 404
    )


def test_create_product_defaults_and_slug(
    commerce_client: TestClient, admin: Headers
) -> None:
    title = unique("Café Mug")
    product = make_product(commerce_client, admin, title=title)
    assert product["status"] == "draft"
    assert product["slug"].startswith("cafe-mug-")
    assert product["description"] == {"type": "doc", "content": []}
    assert product["options"] == [] and product["variants"] == []
    again = make_product(commerce_client, admin, title=title)
    assert again["slug"] == f"{product['slug']}-2"
    custom = make_product(commerce_client, admin, slug="My Custom Slug!")
    assert custom["slug"] == "my-custom-slug"


def test_product_slugs_avoid_storefront_pages(
    commerce_client: TestClient, admin: Headers
) -> None:
    # /shop/cart and /shop/category/<slug> are storefront pages, not products.
    for reserved in ("cart", "Category"):
        product = make_product(commerce_client, admin, slug=reserved)
        assert product["slug"] != reserved.lower()
        assert product["slug"].startswith(f"{reserved.lower()}-")
        renamed = ok(
            commerce_client.patch(
                f"{ADMIN}/products/{product['id']}",
                headers=admin,
                json={"slug": "cart"},
            )
        )
        assert renamed["slug"] != "cart"
    # Categories don't share the product URL space, so they may use the word.
    category = ok(
        commerce_client.post(
            f"{ADMIN}/categories", headers=admin, json={"name": unique("cart")}
        )
    )
    assert category["slug"].startswith("cart-")


def test_update_product_fields(
    commerce_client: TestClient, admin: Headers, storage: FakeStorage
) -> None:
    product = make_product(commerce_client, admin, seo_title="seo")
    image = upload_image(commerce_client, storage, admin)
    updated = ok(
        commerce_client.patch(
            f"{ADMIN}/products/{product['id']}",
            headers=admin,
            json={
                "title": "New title",
                "description": doc("new"),
                "image_file_ids": [image["id"]],
                "seo_title": None,
            },
        )
    )
    assert updated["title"] == "New title"
    assert updated["seo_title"] is None
    assert updated["image_urls"] == [f"/api/v1/files/{image['id']}/content"]
    assert updated["type"] == product["type"]  # the type cannot be changed
    assert updated["slug"] == product["slug"]
    taken = make_product(commerce_client, admin)
    renamed = ok(
        commerce_client.patch(
            f"{ADMIN}/products/{product['id']}",
            headers=admin,
            json={"slug": taken["slug"]},
        )
    )
    assert renamed["slug"] == f"{taken['slug']}-2"
    # Unknown fields such as `type` are ignored; unknown category is 422.
    bad = commerce_client.patch(
        f"{ADMIN}/products/{product['id']}",
        headers=admin,
        json={"category_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert bad.status_code == 422


def test_description_and_image_validation(
    commerce_client: TestClient, admin: Headers, storage: FakeStorage
) -> None:
    bad_node = {"type": "doc", "content": [{"type": "script"}]}
    response = commerce_client.post(
        f"{ADMIN}/products",
        headers=admin,
        json={"type": "digital", "title": "x", "description": bad_node},
    )
    assert response.status_code == 422
    assert "Invalid description" in response.text

    private = upload_image(commerce_client, storage, admin, public=False)
    response = commerce_client.post(
        f"{ADMIN}/products",
        headers=admin,
        json={"type": "digital", "title": "x", "image_file_ids": [private["id"]]},
    )
    assert response.status_code == 422
    assert "public" in response.text

    public = upload_image(commerce_client, storage, admin)
    response = commerce_client.post(
        f"{ADMIN}/products",
        headers=admin,
        json={
            "type": "digital",
            "title": "x",
            "image_file_ids": [public["id"], public["id"]],
        },
    )
    assert response.status_code == 422

    image_doc = {
        "type": "doc",
        "content": [{"type": "image", "attrs": {"fileId": public["id"]}}],
    }
    product = make_product(commerce_client, admin, description=image_doc)
    node = product["description"]["content"][0]
    assert node["attrs"]["src"] == f"/api/v1/files/{public['id']}/content"


def test_options_rules(commerce_client: TestClient, admin: Headers) -> None:
    product = make_product(commerce_client, admin)
    path = f"{ADMIN}/products/{product['id']}/options"
    size = ok(
        commerce_client.post(
            path, headers=admin, json={"name": "Size", "values": ["S", "M"]}
        )
    )
    assert size["position"] == 0 and size["values"] == ["S", "M"]
    dup = commerce_client.post(
        path, headers=admin, json={"name": "size", "values": ["x"]}
    )
    assert dup.status_code == 422
    bad_values = commerce_client.post(
        path, headers=admin, json={"name": "Color", "values": ["a", "A"]}
    )
    assert bad_values.status_code == 422
    for name in ("Color", "Fit"):
        ok(
            commerce_client.post(
                path, headers=admin, json={"name": name, "values": ["a"]}
            )
        )
    fourth = commerce_client.post(
        path, headers=admin, json={"name": "Style", "values": ["a"]}
    )
    assert fourth.status_code == 422
    assert "at most 3" in fourth.text

    # Values can grow; with variants the option is locked.
    grown = ok(
        commerce_client.patch(
            f"{ADMIN}/options/{size['id']}",
            headers=admin,
            json={"values": ["S", "M", "L"]},
        )
    )
    assert grown["values"] == ["S", "M", "L"]

    other = make_product(commerce_client, admin)
    only = ok(
        commerce_client.post(
            f"{ADMIN}/products/{other['id']}/options",
            headers=admin,
            json={"name": "Size", "values": ["S", "M"]},
        )
    )
    make_variant(commerce_client, admin, other["id"], option_values={"Size": "M"})
    assert (
        commerce_client.patch(
            f"{ADMIN}/options/{only['id']}", headers=admin, json={"name": "Width"}
        ).status_code
        == 422
    )
    removing = commerce_client.patch(
        f"{ADMIN}/options/{only['id']}", headers=admin, json={"values": ["S"]}
    )
    assert removing.status_code == 422 and "M" in removing.text
    assert (
        commerce_client.delete(
            f"{ADMIN}/options/{only['id']}", headers=admin
        ).status_code
        == 422
    )
    late = commerce_client.post(
        f"{ADMIN}/products/{other['id']}/options",
        headers=admin,
        json={"name": "Color", "values": ["red"]},
    )
    assert late.status_code == 422
    ok(commerce_client.delete(f"{ADMIN}/options/{size['id']}", headers=admin))


def test_variant_option_value_rules(
    commerce_client: TestClient, admin: Headers
) -> None:
    product = make_product(commerce_client, admin)
    ok(
        commerce_client.post(
            f"{ADMIN}/products/{product['id']}/options",
            headers=admin,
            json={"name": "Size", "values": ["S", "M"]},
        )
    )
    url = f"{ADMIN}/products/{product['id']}/variants"
    for values in ({}, {"Size": "XL"}, {"Size": "S", "Color": "red"}, {"Colour": "S"}):
        response = commerce_client.post(
            url, headers=admin, json={"sku": sku(), "option_values": values}
        )
        assert response.status_code == 422, values
    first_sku = sku()
    first = ok(
        commerce_client.post(
            url,
            headers=admin,
            json={"sku": first_sku.lower(), "option_values": {"Size": "S"}, "stock": 3},
        )
    )
    assert first["sku"] == first_sku  # normalized to upper case
    same_combo = commerce_client.post(
        url, headers=admin, json={"sku": sku(), "option_values": {"Size": "S"}}
    )
    assert same_combo.status_code == 409
    same_sku = commerce_client.post(
        url, headers=admin, json={"sku": first_sku, "option_values": {"Size": "M"}}
    )
    assert same_sku.status_code == 409
    for bad in ("has space", "a/b", ""):
        assert (
            commerce_client.post(
                url, headers=admin, json={"sku": bad, "option_values": {"Size": "M"}}
            ).status_code
            == 422
        )
    negative = commerce_client.post(
        url,
        headers=admin,
        json={"sku": sku(), "option_values": {"Size": "M"}, "stock": -1},
    )
    assert negative.status_code == 422
    # Changing a variant to a taken combination is refused too.
    second = make_variant(
        commerce_client, admin, product["id"], option_values={"Size": "M"}
    )
    clash = commerce_client.patch(
        f"{ADMIN}/variants/{second['id']}",
        headers=admin,
        json={"option_values": {"Size": "S"}},
    )
    assert clash.status_code == 409
    moved = ok(
        commerce_client.patch(
            f"{ADMIN}/variants/{second['id']}",
            headers=admin,
            json={"stock": 9, "position": 7, "is_active": False},
        )
    )
    assert (moved["stock"], moved["position"], moved["is_active"]) == (9, 7, False)
    cleared = ok(
        commerce_client.patch(
            f"{ADMIN}/variants/{second['id']}", headers=admin, json={"stock": None}
        )
    )
    assert cleared["stock"] is None


def test_product_without_options_has_one_variant(
    commerce_client: TestClient, admin: Headers
) -> None:
    product = make_product(commerce_client, admin)
    make_variant(commerce_client, admin, product["id"])
    again = commerce_client.post(
        f"{ADMIN}/products/{product['id']}/variants",
        headers=admin,
        json={"sku": sku()},
    )
    assert again.status_code == 409


def test_prices_and_currencies(commerce_client: TestClient, admin: Headers) -> None:
    product = make_product(commerce_client, admin)
    variant = make_variant(commerce_client, admin, product["id"], stock=1)
    vid = variant["id"]
    price = ok(set_price(commerce_client, admin, vid, "USD", 1234))
    assert price == {"currency": "usd", "amount": 1234, "formatted": "12.34 USD"}
    assert ok(set_price(commerce_client, admin, vid, "usd", 1500))["amount"] == 1500
    yen = ok(set_price(commerce_client, admin, vid, "jpy", 1500))
    assert yen["formatted"] == "1,500 JPY"  # zero-decimal: no cents
    for currency, amount in (("gbp", 100), ("usd", 0), ("usd", -5), ("usd", 10**9)):
        response = set_price(commerce_client, admin, vid, currency, amount)
        assert response.status_code == 422, (currency, amount)
    assert (
        "Allowed: usd, eur, jpy"
        in set_price(commerce_client, admin, vid, "gbp", 100).text
    )
    detail = ok(commerce_client.get(f"{ADMIN}/products/{product['id']}", headers=admin))
    assert [(p["currency"], p["amount"]) for p in detail["variants"][0]["prices"]] == [
        ("jpy", 1500),
        ("usd", 1500),
    ]
    # Inline prices at creation obey the same rules.
    other = make_product(commerce_client, admin)
    created = make_variant(
        commerce_client, admin, other["id"], prices={"eur": 500, "jpy": 700}
    )
    assert {p["currency"] for p in created["prices"]} == {"eur", "jpy"}
    fresh = make_product(commerce_client, admin)
    bad = commerce_client.post(
        f"{ADMIN}/products/{fresh['id']}/variants",
        headers=admin,
        json={"sku": sku(), "prices": {"chf": 5}},
    )
    assert bad.status_code == 422 and "chf" in bad.text
    ok(commerce_client.delete(f"{ADMIN}/variants/{vid}/prices/usd", headers=admin))
    assert (
        commerce_client.delete(
            f"{ADMIN}/variants/{vid}/prices/usd", headers=admin
        ).status_code
        == 404
    )


def test_publish_rules(
    commerce_client: TestClient, admin: Headers, storage: FakeStorage
) -> None:
    publish = lambda pid: commerce_client.post(  # noqa: E731
        f"{ADMIN}/products/{pid}/publish", headers=admin
    )
    # 1. no variant
    physical = make_product(commerce_client, admin, "physical")
    response = publish(physical["id"])
    assert response.status_code == 422 and "active variant" in response.text
    # 2. physical without stock / without price
    variant = make_variant(commerce_client, admin, physical["id"])
    response = publish(physical["id"])
    assert "no price" in response.text and "stock" in response.text
    ok(set_price(commerce_client, admin, variant["id"]))
    assert "stock" in publish(physical["id"]).text
    ok(
        commerce_client.patch(
            f"{ADMIN}/variants/{variant['id']}", headers=admin, json={"stock": 0}
        )
    )
    done = ok(publish(physical["id"]))  # stock 0 is a valid quantity (sold out)
    assert done["status"] == "published" and done["published_at"]

    # 3. digital without file
    digital = make_product(commerce_client, admin, "digital")
    dvariant = make_variant(commerce_client, admin, digital["id"])
    ok(set_price(commerce_client, admin, dvariant["id"]))
    response = publish(digital["id"])
    assert response.status_code == 422 and "no file" in response.text
    file = upload_product_file(commerce_client, storage, admin)
    ok(
        commerce_client.patch(
            f"{ADMIN}/variants/{dvariant['id']}",
            headers=admin,
            json={"file_id": file["id"]},
        )
    )
    first = ok(publish(digital["id"]))
    # unpublish keeps the first publish date; publishing again does not move it
    ok(
        commerce_client.post(
            f"{ADMIN}/products/{digital['id']}/unpublish", headers=admin
        )
    )
    again = ok(publish(digital["id"]))
    assert again["published_at"] == first["published_at"]
    archived = ok(
        commerce_client.post(f"{ADMIN}/products/{digital['id']}/archive", headers=admin)
    )
    assert archived["status"] == "archived"

    # inactive variants are ignored by the rules
    service = make_product(commerce_client, admin, "service")
    live = make_variant(commerce_client, admin, service["id"])
    ok(set_price(commerce_client, admin, live["id"]))
    ok(publish(service["id"]))


def test_published_product_stays_sellable(
    commerce_client: TestClient, admin: Headers, storage: FakeStorage
) -> None:
    product, variant = sellable_product(commerce_client, admin)
    vid = variant["id"]
    # losing the only price, stock, or the only active variant is refused
    assert (
        commerce_client.delete(
            f"{ADMIN}/variants/{vid}/prices/usd", headers=admin
        ).status_code
        == 422
    )
    assert (
        commerce_client.patch(
            f"{ADMIN}/variants/{vid}", headers=admin, json={"stock": None}
        ).status_code
        == 422
    )
    assert (
        commerce_client.patch(
            f"{ADMIN}/variants/{vid}", headers=admin, json={"is_active": False}
        ).status_code
        == 422
    )
    assert (
        commerce_client.delete(f"{ADMIN}/variants/{vid}", headers=admin).status_code
        == 422
    )
    # ...and the refused change was rolled back
    detail = ok(commerce_client.get(f"{ADMIN}/products/{product['id']}", headers=admin))
    assert detail["variants"][0]["stock"] == 5
    assert detail["variants"][0]["is_active"] is True
    assert len(detail["variants"][0]["prices"]) == 1
    # a new active variant without a price cannot be added to a published product
    sized = make_product(commerce_client, admin)
    ok(
        commerce_client.post(
            f"{ADMIN}/products/{sized['id']}/options",
            headers=admin,
            json={"name": "Size", "values": ["S", "M"]},
        )
    )
    small = make_variant(
        commerce_client,
        admin,
        sized["id"],
        option_values={"Size": "S"},
        stock=1,
        prices={"usd": 100},
    )
    ok(commerce_client.post(f"{ADMIN}/products/{sized['id']}/publish", headers=admin))
    url = f"{ADMIN}/products/{sized['id']}/variants"
    unpriced = commerce_client.post(
        url,
        headers=admin,
        json={"sku": sku(), "stock": 1, "option_values": {"Size": "M"}},
    )
    assert unpriced.status_code == 422
    # ...a complete one (or an inactive one) can; the refused one left nothing behind
    assert small["id"]
    make_variant(
        commerce_client,
        admin,
        sized["id"],
        option_values={"Size": "M"},
        stock=2,
        prices={"usd": 200},
    )
    detail = ok(commerce_client.get(f"{ADMIN}/products/{sized['id']}", headers=admin))
    assert len(detail["variants"]) == 2
    # published products cannot be deleted; drafts can
    assert (
        commerce_client.delete(
            f"{ADMIN}/products/{product['id']}", headers=admin
        ).status_code
        == 409
    )
    ok(
        commerce_client.post(
            f"{ADMIN}/products/{product['id']}/unpublish", headers=admin
        )
    )
    ok(commerce_client.delete(f"{ADMIN}/products/{product['id']}", headers=admin))
    assert (
        commerce_client.get(
            f"{ADMIN}/products/{product['id']}", headers=admin
        ).status_code
        == 404
    )


def test_variant_file_rules(
    commerce_client: TestClient,
    admin: Headers,
    storage: FakeStorage,
    make_user: MakeUser,
) -> None:
    digital = make_product(commerce_client, admin, "digital")
    physical = make_product(commerce_client, admin, "physical")
    file = upload_product_file(commerce_client, storage, admin)
    assert file["public"] is False

    # only digital variants can carry a file
    response = commerce_client.post(
        f"{ADMIN}/products/{physical['id']}/variants",
        headers=admin,
        json={"sku": sku(), "file_id": file["id"]},
    )
    assert response.status_code == 422

    # a public image is not a product file
    image = upload_image(commerce_client, storage, admin)
    response = commerce_client.post(
        f"{ADMIN}/products/{digital['id']}/variants",
        headers=admin,
        json={"sku": sku(), "file_id": image["id"]},
    )
    assert response.status_code == 422 and "private" in response.text

    # a member's private file must never be attached (it would be sold to buyers)
    _, member = make_user(UserRole.member)
    theirs = commerce_client.post(
        "/api/v1/files/",
        headers=member,
        json={"filename": "secret.pdf", "content_type": "application/pdf", "size": 10},
    ).json()["file"]
    storage.simulate_upload(f"{theirs['owner_id']}/{theirs['id']}", 10)
    commerce_client.post(f"/api/v1/files/{theirs['id']}/confirm", headers=member)
    response = commerce_client.post(
        f"{ADMIN}/products/{digital['id']}/variants",
        headers=admin,
        json={"sku": sku(), "file_id": theirs["id"]},
    )
    assert response.status_code == 422 and "admin" in response.text

    # unknown and unconfirmed files
    assert (
        commerce_client.post(
            f"{ADMIN}/products/{digital['id']}/variants",
            headers=admin,
            json={"sku": sku(), "file_id": "00000000-0000-0000-0000-000000000009"},
        ).status_code
        == 422
    )
    pending = ok(
        commerce_client.post(
            f"{ADMIN}/files",
            headers=admin,
            json={"filename": "a.pdf", "content_type": "application/pdf", "size": 5},
        )
    )["file"]
    assert (
        commerce_client.post(
            f"{ADMIN}/products/{digital['id']}/variants",
            headers=admin,
            json={"sku": sku(), "file_id": pending["id"]},
        ).status_code
        == 422
    )

    variant = make_variant(commerce_client, admin, digital["id"], file_id=file["id"])
    assert variant["file"]["id"] == file["id"]
    assert variant["file"]["filename"] == "book.pdf"
    public_view = commerce_client.get(f"/api/v1/files/{file['id']}/content")
    assert public_view.status_code == 404  # never public


def test_replacing_or_deleting_a_variant_releases_its_file(
    commerce_client: TestClient, admin: Headers, storage: FakeStorage
) -> None:
    digital = make_product(commerce_client, admin, "digital")
    old = upload_product_file(commerce_client, storage, admin)
    new = upload_product_file(commerce_client, storage, admin)
    variant = make_variant(commerce_client, admin, digital["id"], file_id=old["id"])
    ok(
        commerce_client.patch(
            f"{ADMIN}/variants/{variant['id']}",
            headers=admin,
            json={"file_id": new["id"]},
        )
    )
    old_key = f"{old['owner_id']}/{old['id']}"
    assert old_key in storage.deleted
    assert (
        commerce_client.get(
            f"/api/v1/files/{old['id']}/download", headers=admin
        ).status_code
        == 404
    )
    ok(commerce_client.delete(f"{ADMIN}/variants/{variant['id']}", headers=admin))
    assert f"{new['owner_id']}/{new['id']}" in storage.deleted


def test_deleting_a_draft_product_releases_unshared_files(
    commerce_client: TestClient, admin: Headers, storage: FakeStorage
) -> None:
    file = upload_product_file(commerce_client, storage, admin)
    one = make_product(commerce_client, admin, "digital")
    two = make_product(commerce_client, admin, "digital")
    make_variant(commerce_client, admin, one["id"], file_id=file["id"])
    make_variant(commerce_client, admin, two["id"], file_id=file["id"])
    key = f"{file['owner_id']}/{file['id']}"
    ok(commerce_client.delete(f"{ADMIN}/products/{one['id']}", headers=admin))
    assert key not in storage.deleted  # still used by the other product
    ok(commerce_client.delete(f"{ADMIN}/products/{two['id']}", headers=admin))
    assert key in storage.deleted


def test_admin_product_list_filters(
    commerce_client: TestClient, admin: Headers
) -> None:
    category = ok(
        commerce_client.post(
            f"{ADMIN}/categories", headers=admin, json={"name": unique("Cat")}
        )
    )
    marker = unique("Findme")
    wanted = make_product(
        commerce_client, admin, "digital", title=marker, category_id=category["id"]
    )
    make_product(commerce_client, admin, "physical", title=unique("Other"))
    for params, expected in (
        ({"q": marker.lower()}, 1),
        ({"type": "digital", "category_id": category["id"]}, 1),
        ({"status": "published", "q": marker}, 0),
        ({"status": "draft", "q": marker}, 1),
        ({"q": "%"}, 0),
    ):
        result: dict[str, Any] = ok(
            commerce_client.get(f"{ADMIN}/products", headers=admin, params=params)
        )
        assert result["count"] == expected, params
    page = ok(
        commerce_client.get(f"{ADMIN}/products", headers=admin, params={"limit": 1})
    )
    assert len(page["data"]) == 1 and page["count"] >= 2
    assert wanted["id"] in {
        p["id"]
        for p in ok(
            commerce_client.get(
                f"{ADMIN}/products", headers=admin, params={"q": marker}
            )
        )["data"]
    }

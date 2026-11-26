"""Meta tags for `/shop` pages and the commerce part of `sitemap.xml`."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.modules.commerce.helpers import (
    ADMIN,
    doc,
    make_product,
    ok,
    sellable_product,
    upload_image,
)
from tests.modules.content.test_public_seo import HTML, SITE, make_app
from tests.utils.files import Headers
from tests.utils.storage import FakeStorage

NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


@pytest.fixture
def shop_client(tmp_path: Path) -> TestClient:
    return TestClient(make_app(tmp_path, modules=["items", "commerce"]))


def sitemap_locs(client: TestClient) -> set[str]:
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(r.content)
    return {str(u.findtext("s:loc", namespaces=NS)) for u in root.findall("s:url", NS)}


def test_shop_index_meta(shop_client: TestClient) -> None:
    r = shop_client.get("/shop", headers=HTML)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=60, s-maxage=60"
    assert f"<title>Shop - {settings.PROJECT_NAME}</title>" in r.text
    assert f'<link rel="canonical" href="{SITE}/shop">' in r.text
    assert "Old title" not in r.text


def test_product_meta_uses_seo_fields_image_and_product_type(
    shop_client: TestClient,
    commerce_client: TestClient,
    admin: Headers,
    storage: FakeStorage,
) -> None:
    image = upload_image(commerce_client, storage, admin)
    product, _ = sellable_product(
        commerce_client,
        admin,
        seo_title='Custom <b>"title"</b>',
        seo_description="Seo & description",
        description=doc("Body text"),
        image_file_ids=[image["id"]],
    )
    r = shop_client.get(f"/shop/{product['slug']}", headers=HTML)
    assert r.status_code == 200
    assert "<title>Custom &lt;b&gt;&quot;title&quot;&lt;/b&gt;</title>" in r.text
    assert '<meta name="description" content="Seo &amp; description">' in r.text
    assert f'<link rel="canonical" href="{SITE}/shop/{product["slug"]}">' in r.text
    assert '<meta property="og:type" content="product">' in r.text
    assert (
        f'<meta property="og:image" content="{SITE}/api/v1/files/{image["id"]}/content">'
        in r.text
    )
    assert "Old title" not in r.text
    assert '<script type="module" src="/assets/app.js"></script>' in r.text


def test_product_meta_falls_back_to_title_and_description_text(
    shop_client: TestClient, commerce_client: TestClient, admin: Headers
) -> None:
    product, _ = sellable_product(
        commerce_client, admin, description=doc("Plain   words here")
    )
    r = shop_client.get(f"/shop/{product['slug']}", headers=HTML)
    assert r.status_code == 200
    assert f"<title>{product['title']}</title>" in r.text
    assert '<meta name="description" content="Plain words here">' in r.text
    assert "og:image" not in r.text


def test_empty_description_falls_back_to_title(
    shop_client: TestClient, commerce_client: TestClient, admin: Headers
) -> None:
    product, _ = sellable_product(commerce_client, admin)
    r = shop_client.get(f"/shop/{product['slug']}", headers=HTML)
    assert f'<meta name="description" content="{product["title"]}">' in r.text


def test_unpublished_and_unknown_products_are_404_noindex(
    shop_client: TestClient, commerce_client: TestClient, admin: Headers
) -> None:
    draft, _ = sellable_product(commerce_client, admin, publish=False)
    for slug in (draft["slug"], "no-such-product"):
        r = shop_client.get(f"/shop/{slug}", headers=HTML)
        assert r.status_code == 404
        assert '<meta name="robots" content="noindex">' in r.text
        assert "og:title" not in r.text
        assert r.headers["cache-control"] == "no-cache"


def test_category_meta(
    shop_client: TestClient, commerce_client: TestClient, admin: Headers
) -> None:
    category = ok(
        commerce_client.post(
            f"{ADMIN}/categories", headers=admin, json={"name": "Mugs & Cups"}
        )
    )
    r = shop_client.get(f"/shop/category/{category['slug']}", headers=HTML)
    assert r.status_code == 200
    assert "<title>Mugs &amp; Cups</title>" in r.text
    assert (
        f'<link rel="canonical" href="{SITE}/shop/category/{category["slug"]}">'
        in r.text
    )
    missing = shop_client.get("/shop/category/nope", headers=HTML)
    assert missing.status_code == 404


def test_sitemap_lists_published_products_only(
    shop_client: TestClient, commerce_client: TestClient, admin: Headers
) -> None:
    published, _ = sellable_product(commerce_client, admin)
    draft = make_product(commerce_client, admin)
    locs = sitemap_locs(shop_client)
    assert f"{SITE}/shop" in locs
    assert f"{SITE}/shop/{published['slug']}" in locs
    assert f"{SITE}/shop/{draft['slug']}" not in locs
    r = shop_client.get("/robots.txt")
    assert f"Sitemap: {SITE}/sitemap.xml" in r.text.splitlines()


def test_sitemap_merges_content_and_commerce(
    tmp_path: Path, commerce_client: TestClient, admin: Headers
) -> None:
    product, _ = sellable_product(commerce_client, admin)
    client = TestClient(make_app(tmp_path, modules=["items", "content", "commerce"]))
    locs = sitemap_locs(client)
    assert f"{SITE}/blog" in locs
    assert f"{SITE}/shop/{product['slug']}" in locs


def test_content_sitemap_has_no_shop_urls(tmp_path: Path) -> None:
    client = TestClient(make_app(tmp_path, modules=["items", "content"]))
    assert not any("/shop" in loc for loc in sitemap_locs(client))


def test_module_disabled_has_no_shop_routes(tmp_path: Path) -> None:
    client = TestClient(make_app(tmp_path, modules=["items", "content"]))
    r = client.get("/shop/anything", headers=HTML)
    # The plain SPA shell, untouched: no injected tags.
    assert "<title>Old title</title>" in r.text
    assert "og:type" not in r.text
    off = TestClient(make_app(tmp_path / "off", modules=["items"]))
    assert off.get("/sitemap.xml").status_code == 404
    assert "Sitemap:" not in off.get("/robots.txt").text

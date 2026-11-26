"""SEO helpers of the commerce module: meta values for `/shop` pages and sitemap entries.

Reuses the content module's tag rendering (`PageMeta`, `render_html`); routes live in
`public_routes.py`.
"""

from datetime import datetime
from urllib.parse import quote

from sqlmodel import Session, select

from app.modules import SitemapEntry
from app.modules.commerce import service
from app.modules.commerce.models import Product, ProductCategory, ProductStatus
from app.modules.content.seo import PageMeta

MAX_DESCRIPTION = 300


def shop_index_meta(site_name: str) -> PageMeta:
    return PageMeta(
        title=f"Shop - {site_name}",
        description=f"Products from {site_name}.",
        path="/shop",
    )


def _plain_text(node: object) -> str:
    """Text of a Tiptap JSON tree, blocks separated by spaces."""
    if isinstance(node, dict):
        if node.get("type") == "text":
            text = node.get("text")
            return text if isinstance(text, str) else ""
        children = node.get("content")
        if not isinstance(children, list):
            return ""
        parts = [_plain_text(child) for child in children]
        return " ".join(p for p in parts if p)
    return ""


def _description(product: Product) -> str:
    text = " ".join(_plain_text(product.description).split())
    if len(text) > MAX_DESCRIPTION:
        text = text[: MAX_DESCRIPTION - 1].rstrip() + "…"
    return text


def _first(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def product_meta(session: Session, slug: str, site_url: str) -> PageMeta | None:
    product = session.exec(
        select(Product).where(
            Product.slug == slug, Product.status == ProductStatus.published
        )
    ).first()
    if product is None:
        return None
    images = service.public_image_urls(session, product)
    return PageMeta(
        title=_first(product.seo_title, product.title),
        description=_first(
            product.seo_description, _description(product), product.title
        ),
        path=f"/shop/{quote(product.slug, safe='')}",
        og_type="product",
        image_url=f"{site_url}{images[0]}" if images else None,
    )


def category_meta(session: Session, slug: str) -> PageMeta | None:
    category = session.exec(
        select(ProductCategory).where(ProductCategory.slug == slug)
    ).first()
    if category is None:
        return None
    return PageMeta(
        title=category.name,
        description=f"Products in {category.name}.",
        path=f"/shop/category/{quote(category.slug, safe='')}",
    )


def _date(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None


def sitemap_entries(session: Session) -> list[SitemapEntry]:
    """`/shop` and every published product (sorted by slug)."""
    products = session.exec(
        select(Product.slug, Product.updated_at).where(
            Product.status == ProductStatus.published
        )
    ).all()
    latest = max((updated for _, updated in products), default=None)
    entries: list[SitemapEntry] = [("/shop", _date(latest))]
    entries += [(f"/shop/{quote(s, safe='')}", _date(u)) for s, u in sorted(products)]
    return entries

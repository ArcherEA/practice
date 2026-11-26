"""SEO helpers of the content module: meta tags for the SPA shell, sitemap entries.

The SPA stays a single-page app. For public content URLs the backend returns the built
``index.html`` with the real ``<title>``, description, canonical URL and Open Graph /
Twitter tags, so search engines and link previews see the post. Pure functions here,
routes in ``public_routes.py``.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from sqlmodel import Session, col, func, select

from app.modules import SitemapEntry
from app.modules.content import service
from app.modules.content.models import (
    Category,
    ContentStatus,
    Page,
    Post,
    PostTag,
    Tag,
)

logger = logging.getLogger(__name__)

# Tags we write ourselves; any copy already present in index.html is removed first.
_REPLACED_META = "description|robots|og:[a-z_:]+|twitter:[a-z_:]+|article:[a-z_:]+"
_TITLE_RE = re.compile(r"<title\b[^>]*>.*?</title\s*>", re.IGNORECASE | re.DOTALL)
_META_RE = re.compile(
    rf"<meta\b[^>]*\b(?:name|property)\s*=\s*[\"'](?:{_REPLACED_META})[\"'][^>]*>",
    re.IGNORECASE,
)
_CANONICAL_RE = re.compile(
    r"<link\b[^>]*\brel\s*=\s*[\"']canonical[\"'][^>]*>", re.IGNORECASE
)
_HEAD_END_RE = re.compile(r"</head\s*>", re.IGNORECASE)


@dataclass(frozen=True)
class PageMeta:
    """Values of the tags we inject. ``path`` is the site-relative URL ("/blog/x")."""

    title: str
    description: str
    path: str
    og_type: str = "website"
    image_url: str | None = None
    noindex: bool = False


def absolute_url(site_url: str, path: str) -> str:
    return f"{site_url}{path}"


def meta_tags(meta: PageMeta, *, site_url: str, site_name: str) -> str:
    """The ``<head>`` fragment. Every value is HTML-escaped."""
    title = escape(meta.title)
    lines = [f"<title>{title}</title>"]
    if meta.noindex:
        lines.append('<meta name="robots" content="noindex">')
        return "\n    ".join(lines)
    description = escape(meta.description)
    url = escape(absolute_url(site_url, meta.path))
    lines += [
        f'<meta name="description" content="{description}">',
        f'<link rel="canonical" href="{url}">',
        f'<meta property="og:title" content="{title}">',
        f'<meta property="og:description" content="{description}">',
        f'<meta property="og:type" content="{escape(meta.og_type)}">',
        f'<meta property="og:url" content="{url}">',
        f'<meta property="og:site_name" content="{escape(site_name)}">',
    ]
    if meta.image_url:
        lines.append(f'<meta property="og:image" content="{escape(meta.image_url)}">')
    card = "summary_large_image" if meta.image_url else "summary"
    lines += [
        f'<meta name="twitter:card" content="{card}">',
        f'<meta name="twitter:title" content="{title}">',
        f'<meta name="twitter:description" content="{description}">',
    ]
    if meta.image_url:
        lines.append(f'<meta name="twitter:image" content="{escape(meta.image_url)}">')
    return "\n    ".join(lines)


def load_template(frontend_dir: Path) -> str | None:
    """The built SPA shell, or None when there is no build (local dev)."""
    index = frontend_dir / "index.html"
    try:
        return index.read_text(encoding="utf-8")
    except OSError:
        return None


def render_html(
    template: str | None,
    meta: PageMeta,
    *,
    site_url: str,
    site_name: str,
    spa_url: str,
) -> str:
    """Inject the tags into the SPA ``index.html`` (or a minimal page without one)."""
    tags = meta_tags(meta, site_url=site_url, site_name=site_name)
    if template is None:
        logger.warning(
            "SPA index.html not found; serving a minimal page for %s "
            "(run the frontend build, or use the Vite dev server)",
            meta.path,
        )
        link = escape(f"{spa_url}{meta.path}")
        return (
            '<!doctype html>\n<html lang="en">\n  <head>\n'
            '    <meta charset="utf-8">\n'
            '    <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"    {tags}\n  </head>\n  <body>\n"
            f'    <p><a href="{link}">Open the app</a></p>\n  </body>\n</html>\n'
        )
    html = _TITLE_RE.sub("", template)
    html = _META_RE.sub("", html)
    html = _CANONICAL_RE.sub("", html)
    block = f"    {tags}\n  "
    # Use a function replacement so backslashes in values are not interpreted.
    if _HEAD_END_RE.search(html):
        return _HEAD_END_RE.sub(lambda m: block + m.group(0), html, count=1)
    return f"<head>\n{block}</head>\n{html}"


# --- meta values from the database ---


def _first(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _image(site_url: str, file_id: uuid.UUID | None) -> str | None:
    if file_id is None:
        return None
    return absolute_url(site_url, service.image_url(file_id))


def blog_index_meta(site_name: str) -> PageMeta:
    return PageMeta(
        title=f"Blog - {site_name}",
        description=f"Latest articles from {site_name}.",
        path="/blog",
    )


def post_meta(session: Session, slug: str, site_url: str) -> PageMeta | None:
    post = session.exec(
        select(Post).where(Post.slug == slug, Post.status == ContentStatus.published)
    ).first()
    if post is None:
        return None
    return PageMeta(
        title=_first(post.seo_title, post.title),
        description=_first(post.seo_description, post.excerpt, post.title),
        path=f"/blog/{quote(post.slug, safe='')}",
        og_type="article",
        image_url=_image(site_url, post.cover_file_id),
    )


def page_meta(session: Session, slug: str) -> PageMeta | None:
    page = session.exec(
        select(Page).where(Page.slug == slug, Page.status == ContentStatus.published)
    ).first()
    if page is None:
        return None
    return PageMeta(
        title=_first(page.seo_title, page.title),
        description=_first(page.seo_description, page.title),
        path=f"/p/{quote(page.slug, safe='')}",
    )


def category_meta(session: Session, slug: str) -> PageMeta | None:
    category = session.exec(select(Category).where(Category.slug == slug)).first()
    if category is None:
        return None
    return PageMeta(
        title=category.name,
        description=_first(category.description, f"Posts in {category.name}."),
        path=f"/blog/category/{quote(category.slug, safe='')}",
    )


def tag_meta(session: Session, slug: str) -> PageMeta | None:
    tag = session.exec(select(Tag).where(Tag.slug == slug)).first()
    if tag is None:
        return None
    return PageMeta(
        title=f"Posts tagged {tag.name}",
        description=f"Posts tagged {tag.name}.",
        path=f"/blog/tag/{quote(tag.slug, safe='')}",
    )


def not_found_meta() -> PageMeta:
    return PageMeta(title="Not found", description="", path="", noindex=True)


# --- sitemap and robots ---


def _date(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None


def sitemap_entries(session: Session) -> list[SitemapEntry]:
    """``sitemap.xml`` with published posts and pages, and categories/tags that have posts."""
    entries: list[SitemapEntry] = []

    posts = session.exec(
        select(Post.slug, Post.updated_at).where(Post.status == ContentStatus.published)
    ).all()
    latest = max((updated for _, updated in posts), default=None)
    entries.append(("/blog", _date(latest)))
    entries += [(f"/blog/{quote(s, safe='')}", _date(u)) for s, u in sorted(posts)]

    pages = session.exec(
        select(Page.slug, Page.updated_at).where(Page.status == ContentStatus.published)
    ).all()
    entries += [(f"/p/{quote(s, safe='')}", _date(u)) for s, u in sorted(pages)]

    categories = session.exec(
        select(Category.slug, func.max(Post.updated_at))
        .join(Post, col(Post.category_id) == col(Category.id))
        .where(Post.status == ContentStatus.published)
        .group_by(col(Category.slug))
    ).all()
    entries += [
        (f"/blog/category/{quote(s, safe='')}", _date(u)) for s, u in sorted(categories)
    ]

    tags = session.exec(
        select(Tag.slug, func.max(Post.updated_at))
        .join(PostTag, col(PostTag.tag_id) == col(Tag.id))
        .join(Post, col(Post.id) == col(PostTag.post_id))
        .where(Post.status == ContentStatus.published)
        .group_by(col(Tag.slug))
    ).all()
    entries += [(f"/blog/tag/{quote(s, safe='')}", _date(u)) for s, u in sorted(tags)]

    return entries

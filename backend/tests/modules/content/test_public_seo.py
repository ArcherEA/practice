"""Public SEO routes: meta injection into the SPA shell, sitemap.xml, robots.txt."""

import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import Settings, settings
from app.main import create_app
from app.models import File, FileStatus, User
from app.modules.content import seo
from app.modules.content.models import (
    Category,
    ContentStatus,
    Page,
    Post,
    PostTag,
    Tag,
)

SITE = "https://example.com"
HTML = {"Accept": "text/html"}
SHELL = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Old title</title>
    <meta name="description" content="old description" />
    <meta property="og:title" content="old og" />
    <link rel="canonical" href="https://old.example/" />
    <script type="module" src="/assets/app.js"></script>
  </head>
  <body><div id="root"></div></body>
</html>
"""
NASTY = 'Hack <script>alert("x")</script> & "quotes"'
NASTY_ESCAPED = (
    "Hack &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &quot;quotes&quot;"
)


def uid() -> str:
    return uuid.uuid4().hex[:10]


def make_app(tmp_path: Path, *, modules: list[str], with_build: bool = True) -> FastAPI:
    frontend = tmp_path / "frontend"
    if with_build:
        (frontend / "assets").mkdir(parents=True)
        (frontend / "index.html").write_text(SHELL, encoding="utf-8")
        (frontend / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    app_settings = settings.model_copy(update={"MODULES": modules, "SITE_URL": SITE})
    return create_app(app_settings, frontend_dir=frontend)


@pytest.fixture
def seo_client(tmp_path: Path) -> TestClient:
    return TestClient(make_app(tmp_path, modules=["items", "content"]))


class Seeded:
    def __init__(self) -> None:
        self.cover_id = uuid.uuid4()
        self.category = f"cat-{uid()}"
        self.tag = f"tag-{uid()}"
        self.empty_category = f"empty-cat-{uid()}"
        self.post = f"post-{uid()}"
        self.plain_post = f"plain-{uid()}"
        self.draft = f"draft-{uid()}"
        self.page = f"page-{uid()}"
        self.draft_page = f"draft-page-{uid()}"


@pytest.fixture
def seeded(db: Session) -> Seeded:
    s = Seeded()
    owner = db.exec(select(User)).first()
    assert owner is not None
    db.add(
        File(
            id=s.cover_id,
            owner_id=owner.id,
            key=f"test/{s.cover_id}",
            filename="cover.png",
            content_type="image/png",
            size=10,
            status=FileStatus.ready,
            public=True,
        )
    )
    db.flush()
    category = Category(
        name="News & <Views>", slug=s.category, description='Desc "quoted"'
    )
    empty_category = Category(name="Empty", slug=s.empty_category)
    tag = Tag(name="Tag <b>", slug=s.tag)
    db.add_all([category, empty_category, tag])
    db.flush()
    updated = datetime(2026, 3, 4, 12, 0, tzinfo=UTC)
    post = Post(
        title=NASTY,
        slug=s.post,
        excerpt="Excerpt <i>text</i>",
        body={"type": "doc", "content": []},
        cover_file_id=s.cover_id,
        category_id=category.id,
        seo_title=None,
        seo_description=None,
        updated_at=updated,
        status=ContentStatus.published,
        published_at=updated,
    )
    plain = Post(
        title="Plain",
        slug=s.plain_post,
        excerpt="ignored",
        seo_title="SEO title",
        seo_description="SEO description",
        body={"type": "doc", "content": []},
        updated_at=updated,
        status=ContentStatus.published,
        published_at=updated,
    )
    draft = Post(title="Draft", slug=s.draft, body={"type": "doc", "content": []})
    page = Page(
        title="About us",
        slug=s.page,
        body={"type": "doc", "content": []},
        updated_at=updated,
        status=ContentStatus.published,
        published_at=updated,
    )
    draft_page = Page(
        title="Hidden", slug=s.draft_page, body={"type": "doc", "content": []}
    )
    db.add_all([post, plain, draft, page, draft_page])
    db.flush()
    db.add(PostTag(post_id=post.id, tag_id=tag.id))
    db.add(PostTag(post_id=draft.id, tag_id=tag.id))
    db.commit()
    return s


def test_post_tags_are_injected_and_escaped(
    seo_client: TestClient, seeded: Seeded
) -> None:
    r = seo_client.get(f"/blog/{seeded.post}", headers=HTML)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "public, max-age=60, s-maxage=60"
    body = r.text
    url = f"{SITE}/blog/{seeded.post}"
    assert f"<title>{NASTY_ESCAPED}</title>" in body
    assert "<script>alert" not in body
    assert '<meta name="description" content="Excerpt &lt;i&gt;text&lt;/i&gt;">' in body
    assert f'<link rel="canonical" href="{url}">' in body
    assert f'<meta property="og:title" content="{NASTY_ESCAPED}">' in body
    assert '<meta property="og:type" content="article">' in body
    assert f'<meta property="og:url" content="{url}">' in body
    assert f'<meta property="og:site_name" content="{settings.PROJECT_NAME}">' in body
    image = f"{SITE}/api/v1/files/{seeded.cover_id}/content"
    assert f'<meta property="og:image" content="{image}">' in body
    assert '<meta name="twitter:card" content="summary_large_image">' in body
    assert f'<meta name="twitter:image" content="{image}">' in body
    # The shell is kept and the old tags are gone.
    assert '<script type="module" src="/assets/app.js"></script>' in body
    assert "Old title" not in body
    assert "old description" not in body
    assert "old og" not in body
    assert "old.example" not in body
    assert body.count("<title>") == 1
    assert body.count('rel="canonical"') == 1


def test_post_seo_fields_win_and_no_image_without_cover(
    seo_client: TestClient, seeded: Seeded
) -> None:
    body = seo_client.get(f"/blog/{seeded.plain_post}", headers=HTML).text
    assert "<title>SEO title</title>" in body
    assert '<meta name="description" content="SEO description">' in body
    assert "og:image" not in body
    assert '<meta name="twitter:card" content="summary">' in body


def test_page_tags(seo_client: TestClient, seeded: Seeded) -> None:
    r = seo_client.get(f"/p/{seeded.page}", headers=HTML)
    assert r.status_code == 200
    assert "<title>About us</title>" in r.text
    assert f'<link rel="canonical" href="{SITE}/p/{seeded.page}">' in r.text
    assert '<meta property="og:type" content="website">' in r.text


def test_category_and_tag_tags(seo_client: TestClient, seeded: Seeded) -> None:
    r = seo_client.get(f"/blog/category/{seeded.category}", headers=HTML)
    assert r.status_code == 200
    assert "<title>News &amp; &lt;Views&gt;</title>" in r.text
    assert '<meta name="description" content="Desc &quot;quoted&quot;">' in r.text
    assert f"{SITE}/blog/category/{seeded.category}" in r.text

    r = seo_client.get(f"/blog/tag/{seeded.tag}", headers=HTML)
    assert r.status_code == 200
    assert "<title>Posts tagged Tag &lt;b&gt;</title>" in r.text
    assert f"{SITE}/blog/tag/{seeded.tag}" in r.text


def test_blog_index_tags(seo_client: TestClient) -> None:
    r = seo_client.get("/blog", headers=HTML)
    assert r.status_code == 200
    assert f"<title>Blog - {settings.PROJECT_NAME}</title>" in r.text
    assert f'<link rel="canonical" href="{SITE}/blog">' in r.text


@pytest.mark.parametrize(
    "path",
    [
        "/blog/{post_draft}",
        "/blog/does-not-exist",
        "/blog/category/does-not-exist",
        "/blog/tag/does-not-exist",
        "/p/{page_draft}",
        "/p/does-not-exist",
    ],
)
def test_unknown_and_draft_are_404_noindex(
    seo_client: TestClient, seeded: Seeded, path: str
) -> None:
    path = path.format(post_draft=seeded.draft, page_draft=seeded.draft_page)
    r = seo_client.get(path, headers=HTML)
    assert r.status_code == 404
    assert '<meta name="robots" content="noindex">' in r.text
    assert "canonical" not in r.text
    assert "og:title" not in r.text
    # Still the SPA shell, so the SPA can render its own not-found page.
    assert '<script type="module" src="/assets/app.js"></script>' in r.text
    assert r.headers["cache-control"] == "no-cache"


def test_module_disabled_has_no_public_routes(tmp_path: Path) -> None:
    client = TestClient(make_app(tmp_path, modules=["items"]))
    for path in ("/blog", "/blog/x", "/p/x", "/blog/tag/x", "/sitemap.xml"):
        r = client.get(path)
        assert r.status_code == 404
        assert "og:title" not in r.text
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Sitemap:" not in robots.text
    assert "Disallow: /api/" in robots.text


def test_robots_with_content(seo_client: TestClient) -> None:
    r = seo_client.get("/robots.txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    lines = r.text.splitlines()
    assert "User-agent: *" in lines
    assert "Allow: /" in lines
    for path in ("/content/", "/admin", "/settings", "/api/"):
        assert f"Disallow: {path}" in lines
    assert f"Sitemap: {SITE}/sitemap.xml" in lines


def test_sitemap_lists_only_published_items(
    seo_client: TestClient, seeded: Seeded
) -> None:
    r = seo_client.get("/sitemap.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.fromstring(r.content)
    urls = {
        u.findtext("s:loc", namespaces=ns): u.findtext("s:lastmod", namespaces=ns)
        for u in root.findall("s:url", ns)
    }
    assert all(loc is not None and loc.startswith(f"{SITE}/") for loc in urls)
    assert urls[f"{SITE}/blog"] is not None
    assert urls[f"{SITE}/blog/{seeded.post}"] == "2026-03-04"
    assert urls[f"{SITE}/blog/{seeded.plain_post}"] == "2026-03-04"
    assert urls[f"{SITE}/p/{seeded.page}"] == "2026-03-04"
    assert urls[f"{SITE}/blog/category/{seeded.category}"] == "2026-03-04"
    assert urls[f"{SITE}/blog/tag/{seeded.tag}"] == "2026-03-04"
    joined = "\n".join(str(loc) for loc in urls)
    assert seeded.draft not in joined
    assert seeded.draft_page not in joined
    assert seeded.empty_category not in joined  # no published posts


def test_without_index_html_a_minimal_page_is_served(
    tmp_path: Path, seeded: Seeded, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(
        make_app(tmp_path, modules=["items", "content"], with_build=False)
    )
    # Alembic's fileConfig (run by the test DB setup) disables existing loggers,
    # so record the warning call instead of relying on caplog.
    warnings: list[str] = []
    monkeypatch.setattr(
        seo.logger, "warning", lambda msg, *args: warnings.append(msg % args)
    )
    r = client.get(f"/blog/{seeded.post}")
    assert r.status_code == 200
    assert r.text.startswith("<!doctype html>")
    assert f"<title>{NASTY_ESCAPED}</title>" in r.text
    assert f'<link rel="canonical" href="{SITE}/blog/{seeded.post}">' in r.text
    assert f'href="{settings.FRONTEND_HOST}/blog/{seeded.post}"' in r.text
    assert any("index.html not found" in w for w in warnings)

    missing = client.get(f"/blog/{seeded.draft}")
    assert missing.status_code == 404
    assert 'content="noindex"' in missing.text


def test_precedence_over_the_frontend_mount(
    seo_client: TestClient, seeded: Seeded
) -> None:
    # SEO route beats the mount, with injected tags...
    r = seo_client.get(f"/blog/{seeded.plain_post}", headers=HTML)
    assert "<title>SEO title</title>" in r.text
    # ...while static files and SPA deep links still go to the frontend mount.
    asset = seo_client.get("/assets/app.js")
    assert asset.status_code == 200
    assert asset.text == "console.log(1)"
    deep = seo_client.get("/dashboard", headers=HTML)
    assert deep.status_code == 200
    assert "<title>Old title</title>" in deep.text
    # API routes are untouched.
    assert seo_client.get("/api/v1/utils/health-check/").json() is True


def test_seo_routes_are_not_in_openapi(seo_client: TestClient) -> None:
    paths = seo_client.get("/api/v1/openapi.json").json()["paths"]
    assert not [p for p in paths if not p.startswith("/api/")]


def test_site_url_trailing_slash_is_stripped() -> None:
    overrides: dict[str, str] = {"SITE_URL": "https://example.com/"}
    s = Settings(**overrides)  # type: ignore[arg-type] # env supplies the required fields
    assert s.SITE_URL == "https://example.com"

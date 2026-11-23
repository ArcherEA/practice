"""Public routes outside ``/api``: SPA pages with real meta tags, and ``sitemap.xml``.

Included by ``create_app`` before the SPA mount so they take precedence over it. They
are hidden from the OpenAPI schema (the generated client only covers ``/api``).
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from app.api.deps import SessionDep
from app.core.config import Settings
from app.modules.content import seo

router = APIRouter(include_in_schema=False)

CACHE_OK = "public, max-age=60, s-maxage=60"
CACHE_MISS = "no-cache"


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _frontend_dir(request: Request) -> Path:
    frontend_dir: Path = request.app.state.frontend_dir
    return frontend_dir


SettingsDep = Annotated[Settings, Depends(_settings)]
FrontendDirDep = Annotated[Path, Depends(_frontend_dir)]


def _respond(
    meta: seo.PageMeta | None, settings: Settings, frontend_dir: Path
) -> HTMLResponse:
    """200 with the injected page, or the same SPA shell with 404 + noindex."""
    found = meta is not None
    html = seo.render_html(
        seo.load_template(frontend_dir),
        meta if meta is not None else seo.not_found_meta(),
        site_url=settings.SITE_URL,
        site_name=settings.PROJECT_NAME,
        spa_url=settings.FRONTEND_HOST,
    )
    return HTMLResponse(
        html,
        status_code=200 if found else 404,
        headers={"Cache-Control": CACHE_OK if found else CACHE_MISS},
    )


@router.get("/blog", response_class=HTMLResponse)
def blog_index(settings: SettingsDep, frontend_dir: FrontendDirDep) -> HTMLResponse:
    return _respond(seo.blog_index_meta(settings.PROJECT_NAME), settings, frontend_dir)


@router.get("/blog/category/{slug}", response_class=HTMLResponse)
def blog_category(
    slug: str, session: SessionDep, settings: SettingsDep, frontend_dir: FrontendDirDep
) -> HTMLResponse:
    return _respond(seo.category_meta(session, slug), settings, frontend_dir)


@router.get("/blog/tag/{slug}", response_class=HTMLResponse)
def blog_tag(
    slug: str, session: SessionDep, settings: SettingsDep, frontend_dir: FrontendDirDep
) -> HTMLResponse:
    return _respond(seo.tag_meta(session, slug), settings, frontend_dir)


@router.get("/blog/{slug}", response_class=HTMLResponse)
def blog_post(
    slug: str, session: SessionDep, settings: SettingsDep, frontend_dir: FrontendDirDep
) -> HTMLResponse:
    meta = seo.post_meta(session, slug, settings.SITE_URL)
    return _respond(meta, settings, frontend_dir)


@router.get("/p/{slug}", response_class=HTMLResponse)
def public_page(
    slug: str, session: SessionDep, settings: SettingsDep, frontend_dir: FrontendDirDep
) -> HTMLResponse:
    return _respond(seo.page_meta(session, slug), settings, frontend_dir)


@router.get("/sitemap.xml")
def sitemap(session: SessionDep, settings: SettingsDep) -> Response:
    return Response(
        seo.build_sitemap(session, settings.SITE_URL),
        media_type="application/xml",
        headers={"Cache-Control": CACHE_OK},
    )

"""Public routes outside ``/api`` for the commerce module: shop pages with meta tags.

Mounted before the SPA, only when the commerce module is enabled. Same pattern as the
content module. An unknown product or category gets the SPA shell with 404 + noindex.
The URLs of published products are added to ``sitemap.xml`` through the module's
``sitemap_entries`` (see ``app.api.public``).
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.api.deps import SessionDep
from app.core.config import Settings
from app.modules.commerce import seo as commerce_seo
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


@router.get("/shop", response_class=HTMLResponse)
def shop_index(settings: SettingsDep, frontend_dir: FrontendDirDep) -> HTMLResponse:
    return _respond(
        commerce_seo.shop_index_meta(settings.PROJECT_NAME), settings, frontend_dir
    )


@router.get("/shop/category/{slug}", response_class=HTMLResponse)
def shop_category(
    slug: str, session: SessionDep, settings: SettingsDep, frontend_dir: FrontendDirDep
) -> HTMLResponse:
    meta = commerce_seo.category_meta(session, slug)
    return _respond(meta, settings, frontend_dir)


@router.get("/shop/{slug}", response_class=HTMLResponse)
def shop_product(
    slug: str, session: SessionDep, settings: SettingsDep, frontend_dir: FrontendDirDep
) -> HTMLResponse:
    meta = commerce_seo.product_meta(session, slug, settings.SITE_URL)
    return _respond(meta, settings, frontend_dir)

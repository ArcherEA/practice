"""Public routes outside ``/api`` for the community module: profile pages with meta tags.

Mounted before the SPA, only when the community module is enabled. An unknown user
falls back to the plain SPA shell (the app renders its own "not found").
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.api.deps import SessionDep
from app.core.config import Settings
from app.modules.community import seo as community_seo
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


@router.get("/u/{username}", response_class=HTMLResponse)
def profile_page(
    username: str,
    session: SessionDep,
    settings: SettingsDep,
    frontend_dir: FrontendDirDep,
) -> HTMLResponse:
    meta = community_seo.profile_meta(session, username, settings.PROJECT_NAME)
    template = seo.load_template(frontend_dir)
    if meta is None:
        # Plain index: the SPA shows its own not-found page for the profile.
        return HTMLResponse(
            template if template is not None else "",
            headers={"Cache-Control": CACHE_MISS},
        )
    html = seo.render_html(
        template,
        meta,
        site_url=settings.SITE_URL,
        site_name=settings.PROJECT_NAME,
        spa_url=settings.FRONTEND_HOST,
    )
    return HTMLResponse(html, headers={"Cache-Control": CACHE_OK})

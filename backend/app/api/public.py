"""Core routes outside ``/api`` that are always on (robots.txt)."""

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.core.config import Settings

router = APIRouter(include_in_schema=False)


def build_robots(site_url: str, *, with_sitemap: bool) -> str:
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /content/",
        "Disallow: /admin",
        "Disallow: /settings",
        "Disallow: /api/",
    ]
    if with_sitemap:
        lines += ["", f"Sitemap: {site_url}/sitemap.xml"]
    return "\n".join(lines) + "\n"


@router.get("/robots.txt")
def robots(request: Request) -> PlainTextResponse:
    """Always served; the Sitemap line only exists when the content module is on."""
    settings: Settings = request.app.state.settings
    body = build_robots(settings.SITE_URL, with_sitemap="content" in settings.MODULES)
    return PlainTextResponse(body, headers={"Cache-Control": "public, max-age=3600"})

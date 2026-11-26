"""Core routes outside ``/api``: robots.txt and the combined sitemap.xml."""

import xml.etree.ElementTree as ET

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

from app.api.deps import SessionDep
from app.core.config import Settings
from app.modules import SitemapEntry
from app.modules.registry import enabled_modules

router = APIRouter(include_in_schema=False)

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
CACHE_OK = "public, max-age=60, s-maxage=60"


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


def _has_sitemap(settings: Settings) -> bool:
    return any(m.sitemap_entries for m in enabled_modules(settings.MODULES))


def build_sitemap(entries: list[SitemapEntry], site_url: str) -> bytes:
    urlset = ET.Element("urlset", xmlns=SITEMAP_NS)
    for path, lastmod in entries:
        url = ET.SubElement(urlset, "url")
        ET.SubElement(url, "loc").text = f"{site_url}{path}"
        if lastmod:
            ET.SubElement(url, "lastmod").text = lastmod
    # typeshed types this call as Any when xml_declaration is given.
    xml: bytes = ET.tostring(urlset, encoding="utf-8", xml_declaration=True)
    return xml


@router.get("/robots.txt")
def robots(request: Request) -> PlainTextResponse:
    """Always served; the Sitemap line only exists when a module adds sitemap URLs."""
    settings: Settings = request.app.state.settings
    body = build_robots(settings.SITE_URL, with_sitemap=_has_sitemap(settings))
    return PlainTextResponse(body, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/sitemap.xml")
def sitemap(request: Request, session: SessionDep) -> Response:
    """One sitemap with the URLs of every enabled module (content, commerce)."""
    settings: Settings = request.app.state.settings
    if not _has_sitemap(settings):
        raise HTTPException(status_code=404)
    entries: list[SitemapEntry] = []
    for module in enabled_modules(settings.MODULES):
        if module.sitemap_entries is not None:
            entries += module.sitemap_entries(session)
    return Response(
        build_sitemap(entries, settings.SITE_URL),
        media_type="application/xml",
        headers={"Cache-Control": CACHE_OK},
    )

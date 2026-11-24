"""Meta tags for public profile pages (`/u/{username}`), following the content SEO pattern.

Profiles are deliberately not in the sitemap (privacy). Unknown or inactive users get no
meta, so the caller falls back to the plain SPA shell.
"""

from urllib.parse import quote

from sqlmodel import Session, select

from app.models import User
from app.modules.community import service
from app.modules.content.seo import PageMeta


def profile_meta(session: Session, username: str, site_name: str) -> PageMeta | None:
    user = session.exec(select(User).where(User.username == username.lower())).first()
    if user is None or not user.is_active:
        return None
    name = service.display_name(user)
    bio = (user.bio or "").strip()
    return PageMeta(
        title=f"{name} (@{user.username})",
        description=bio or f"{name} on {site_name}.",
        path=f"/u/{quote(user.username, safe='')}",
        og_type="profile",
    )

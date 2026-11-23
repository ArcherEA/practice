"""Meta tags for `/u/{username}`: injected for active users, absent otherwise."""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import User
from tests.modules.content.test_public_seo import HTML, SITE, make_app
from tests.utils.files import Headers

MakeUser = Callable[..., tuple[User, Headers]]


def set_profile(
    db: Session,
    user: User,
    *,
    username: str,
    full_name: str | None,
    bio: str | None,
    active: bool = True,
) -> None:
    row = db.get(User, user.id)
    assert row is not None
    row.username = username
    row.full_name = full_name
    row.bio = bio
    row.is_active = active
    db.add(row)
    db.commit()


def test_profile_tags_are_injected_and_escaped(
    tmp_path: Path, db: Session, make_user: MakeUser
) -> None:
    user, _ = make_user()
    set_profile(
        db, user, username="seo_ada", full_name="Ada <b>L</b>", bio='Hi & "bye"'
    )
    client = TestClient(make_app(tmp_path, modules=["items", "content", "community"]))
    r = client.get("/u/SEO_Ada", headers=HTML)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=60, s-maxage=60"
    assert "<title>Ada &lt;b&gt;L&lt;/b&gt; (@seo_ada)</title>" in r.text
    assert '<meta name="description" content="Hi &amp; &quot;bye&quot;">' in r.text
    assert f'<link rel="canonical" href="{SITE}/u/seo_ada">' in r.text
    assert "Old title" not in r.text
    assert '<script type="module" src="/assets/app.js"></script>' in r.text


def test_profile_without_bio_has_a_default_description(
    tmp_path: Path, db: Session, make_user: MakeUser
) -> None:
    user, _ = make_user()
    set_profile(db, user, username="seo_nobio", full_name="Bob", bio=None)
    client = TestClient(make_app(tmp_path, modules=["items", "content", "community"]))
    r = client.get("/u/seo_nobio", headers=HTML)
    assert "<title>Bob (@seo_nobio)</title>" in r.text
    assert '<meta name="description" content="Bob on ' in r.text


def test_unknown_and_inactive_users_get_the_plain_index(
    tmp_path: Path, db: Session, make_user: MakeUser
) -> None:
    user, _ = make_user()
    set_profile(
        db, user, username="seo_gone", full_name="Gone", bio="secret", active=False
    )
    client = TestClient(make_app(tmp_path, modules=["items", "content", "community"]))
    for name in ("seo_gone", "does_not_exist"):
        r = client.get(f"/u/{name}", headers=HTML)
        assert r.status_code == 200
        assert "<title>Old title</title>" in r.text
        assert "secret" not in r.text
        assert "/u/" not in r.text


def test_route_only_exists_with_the_community_module(
    tmp_path: Path, db: Session, make_user: MakeUser
) -> None:
    user, _ = make_user()
    set_profile(db, user, username="seo_off", full_name="Off", bio="x")
    client = TestClient(make_app(tmp_path, modules=["items", "content"]))
    r = client.get("/u/seo_off", headers=HTML)
    assert "(@seo_off)" not in r.text


def test_profiles_are_not_in_the_sitemap(
    tmp_path: Path, db: Session, make_user: MakeUser
) -> None:
    user, _ = make_user()
    set_profile(db, user, username="seo_map", full_name="Map", bio="x")
    client = TestClient(make_app(tmp_path, modules=["items", "content", "community"]))
    assert "/u/" not in client.get("/sitemap.xml").text

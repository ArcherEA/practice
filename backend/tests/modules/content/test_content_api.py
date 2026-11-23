import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.roles import UserRole, has_role
from app.models import File, User
from app.modules.content import service
from app.modules.content.models import Page, Post
from tests.utils.files import Headers, MakeUser, upload_ready
from tests.utils.storage import FakeStorage
from tests.utils.utils import random_lower_string

BASE = f"{settings.API_V1_STR}/content"
MANAGE = f"{BASE}/manage"


def doc(*content: dict[str, Any]) -> dict[str, Any]:
    return {"type": "doc", "content": list(content)}


def para(value: str = "hello") -> dict[str, Any]:
    return {"type": "paragraph", "content": [{"type": "text", "text": value}]}


def unique_title(prefix: str = "Post") -> str:
    return f"{prefix} {random_lower_string()[:12]}"


@pytest.fixture
def editor(make_user: MakeUser) -> tuple[User, Headers]:
    return make_user(UserRole.editor)


def create_post(client: TestClient, headers: Headers, **fields: Any) -> dict[str, Any]:
    payload = {"title": unique_title(), **fields}
    response = client.post(f"{MANAGE}/posts", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def create_page(client: TestClient, headers: Headers, **fields: Any) -> dict[str, Any]:
    payload = {"title": unique_title("Page"), **fields}
    response = client.post(f"{MANAGE}/pages", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def make_image(
    client: TestClient,
    storage: FakeStorage,
    headers: Headers,
    *,
    public: bool = True,
    content_type: str = "image/png",
) -> dict[str, Any]:
    return upload_ready(
        client,
        storage,
        headers,
        content_type=content_type,
        filename="pic.png",
        public=public,
    )


def make_category(
    client: TestClient, headers: Headers, **fields: Any
) -> dict[str, Any]:
    payload = {"name": unique_title("Cat"), **fields}
    response = client.post(f"{MANAGE}/categories", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def make_tag(client: TestClient, headers: Headers, **fields: Any) -> dict[str, Any]:
    payload = {"name": unique_title("Tag"), **fields}
    response = client.post(f"{MANAGE}/tags", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


# --- permissions ---

SOME_ID = "00000000-0000-0000-0000-000000000001"
MANAGE_ENDPOINTS: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", f"{MANAGE}/posts", None),
    ("POST", f"{MANAGE}/posts", {"title": "x"}),
    ("GET", f"{MANAGE}/posts/{SOME_ID}", None),
    ("PUT", f"{MANAGE}/posts/{SOME_ID}", {"title": "x"}),
    ("POST", f"{MANAGE}/posts/{SOME_ID}/publish", None),
    ("POST", f"{MANAGE}/posts/{SOME_ID}/unpublish", None),
    ("DELETE", f"{MANAGE}/posts/{SOME_ID}", None),
    ("GET", f"{MANAGE}/pages", None),
    ("POST", f"{MANAGE}/pages", {"title": "x"}),
    ("GET", f"{MANAGE}/pages/{SOME_ID}", None),
    ("PUT", f"{MANAGE}/pages/{SOME_ID}", {"title": "x"}),
    ("POST", f"{MANAGE}/pages/{SOME_ID}/publish", None),
    ("POST", f"{MANAGE}/pages/{SOME_ID}/unpublish", None),
    ("DELETE", f"{MANAGE}/pages/{SOME_ID}", None),
    ("POST", f"{MANAGE}/categories", {"name": "x"}),
    ("PUT", f"{MANAGE}/categories/{SOME_ID}", {"name": "x"}),
    ("DELETE", f"{MANAGE}/categories/{SOME_ID}", None),
    ("POST", f"{MANAGE}/tags", {"name": "x"}),
    ("PUT", f"{MANAGE}/tags/{SOME_ID}", {"name": "x"}),
    ("DELETE", f"{MANAGE}/tags/{SOME_ID}", None),
]


@pytest.mark.parametrize(("method", "path", "payload"), MANAGE_ENDPOINTS)
def test_manage_endpoints_require_authentication(
    content_client: TestClient, method: str, path: str, payload: dict[str, Any] | None
) -> None:
    response = content_client.request(method, path, json=payload)
    assert response.status_code == 401


@pytest.mark.parametrize("role", [UserRole.member, UserRole.moderator])
@pytest.mark.parametrize(("method", "path", "payload"), MANAGE_ENDPOINTS)
def test_manage_endpoints_forbid_member_and_moderator(
    content_client: TestClient,
    make_user: MakeUser,
    role: UserRole,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    _, headers = make_user(role)
    response = content_client.request(method, path, headers=headers, json=payload)
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("role", "superuser"),
    [
        (UserRole.editor, False),
        (UserRole.admin, False),
        (UserRole.member, True),
        (UserRole.moderator, True),
    ],
)
def test_editor_admin_and_superuser_can_write(
    content_client: TestClient, make_user: MakeUser, role: UserRole, superuser: bool
) -> None:
    _, headers = make_user(role, superuser)
    post = create_post(content_client, headers)
    page = create_page(content_client, headers)
    r = content_client.delete(f"{MANAGE}/posts/{post['id']}", headers=headers)
    assert r.status_code == 200
    r = content_client.delete(f"{MANAGE}/pages/{page['id']}", headers=headers)
    assert r.status_code == 200


def test_editor_role_semantics(make_user: MakeUser) -> None:
    """Pins the hierarchy the content module relies on."""
    users = {role: make_user(role)[0] for role in UserRole}
    assert has_role(users[UserRole.editor], UserRole.editor)
    assert has_role(users[UserRole.admin], UserRole.editor)
    assert not has_role(users[UserRole.moderator], UserRole.editor)
    assert not has_role(users[UserRole.member], UserRole.editor)
    superuser, _ = make_user(UserRole.member, True)
    assert has_role(superuser, UserRole.editor)


def test_public_endpoints_need_no_auth(content_client: TestClient) -> None:
    for path in ("/posts", "/categories", "/tags"):
        assert content_client.get(f"{BASE}{path}").status_code == 200


# --- posts: lifecycle and visibility ---


def test_create_post_defaults(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    user, headers = editor
    post = create_post(
        content_client,
        headers,
        title="My First Post",
        excerpt="short",
        seo_title="SEO t",
        seo_description="SEO d",
    )
    assert post["status"] == "draft"
    assert post["published_at"] is None
    assert post["author_id"] == str(user.id)
    assert post["body"] == {"type": "doc", "content": []}
    assert post["excerpt"] == "short"
    assert post["seo_title"] == "SEO t"
    assert post["seo_description"] == "SEO d"
    assert post["tags"] == []
    assert post["category"] is None
    assert post["cover_url"] is None
    assert post["slug"].startswith("my-first-post")


def test_draft_is_invisible_publicly_until_published(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    category = make_category(content_client, headers)
    post = create_post(content_client, headers, category_id=category["id"])

    # Draft: hidden from the public list and by-slug endpoint, even when authenticated.
    listing = content_client.get(f"{BASE}/posts", params={"category": category["slug"]})
    assert listing.json() == {"data": [], "count": 0}
    assert content_client.get(f"{BASE}/posts/{post['slug']}").status_code == 404
    assert (
        content_client.get(f"{BASE}/posts/{post['slug']}", headers=headers).status_code
        == 404
    )
    # ... but editors see it in the manage list and by id.
    manage = content_client.get(
        f"{MANAGE}/posts", headers=headers, params={"category": category["slug"]}
    )
    assert manage.json()["count"] == 1
    assert (
        content_client.get(f"{MANAGE}/posts/{post['id']}", headers=headers).status_code
        == 200
    )

    published = content_client.post(
        f"{MANAGE}/posts/{post['id']}/publish", headers=headers
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    first_published_at = published.json()["published_at"]
    assert first_published_at is not None

    listing = content_client.get(f"{BASE}/posts", params={"category": category["slug"]})
    assert listing.json()["count"] == 1
    item = listing.json()["data"][0]
    assert item["slug"] == post["slug"]
    assert "body" not in item  # lists are summaries
    public = content_client.get(f"{BASE}/posts/{post['slug']}")
    assert public.status_code == 200
    assert public.json()["id"] == post["id"]

    # Publishing again keeps the original date.
    again = content_client.post(f"{MANAGE}/posts/{post['id']}/publish", headers=headers)
    assert again.json()["published_at"] == first_published_at

    # Unpublish returns to draft and hides it again; the date is kept for a republish.
    draft = content_client.post(
        f"{MANAGE}/posts/{post['id']}/unpublish", headers=headers
    )
    assert draft.json()["status"] == "draft"
    assert draft.json()["published_at"] == first_published_at
    assert content_client.get(f"{BASE}/posts/{post['slug']}").status_code == 404
    republished = content_client.post(
        f"{MANAGE}/posts/{post['id']}/publish", headers=headers
    )
    assert republished.json()["published_at"] == first_published_at


def test_manage_list_filters_and_pagination(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    tag = make_tag(content_client, headers)
    ids = []
    for i in range(3):
        post = create_post(
            content_client,
            headers,
            title=f"Paged {tag['slug']} {i}",
            tag_ids=[tag["id"]],
        )
        ids.append(post["id"])
    content_client.post(f"{MANAGE}/posts/{ids[0]}/publish", headers=headers)

    everything = content_client.get(
        f"{MANAGE}/posts", headers=headers, params={"tag": tag["slug"]}
    ).json()
    assert everything["count"] == 3
    drafts = content_client.get(
        f"{MANAGE}/posts",
        headers=headers,
        params={"tag": tag["slug"], "status": "draft"},
    ).json()
    assert drafts["count"] == 2
    published = content_client.get(
        f"{MANAGE}/posts",
        headers=headers,
        params={"tag": tag["slug"], "status": "published"},
    ).json()
    assert published["count"] == 1
    searched = content_client.get(
        f"{MANAGE}/posts",
        headers=headers,
        params={"tag": tag["slug"], "q": f"{tag['slug']} 1"},
    ).json()
    assert [p["id"] for p in searched["data"]] == [ids[1]]
    # LIKE wildcards in the search text are literal
    wildcard = content_client.get(
        f"{MANAGE}/posts", headers=headers, params={"q": "%_nothing_%"}
    ).json()
    assert wildcard["count"] == 0

    page1 = content_client.get(
        f"{MANAGE}/posts",
        headers=headers,
        params={"tag": tag["slug"], "limit": 2, "skip": 0},
    ).json()
    page2 = content_client.get(
        f"{MANAGE}/posts",
        headers=headers,
        params={"tag": tag["slug"], "limit": 2, "skip": 2},
    ).json()
    assert page1["count"] == page2["count"] == 3
    assert len(page1["data"]) == 2
    assert len(page2["data"]) == 1
    assert {p["id"] for p in page1["data"] + page2["data"]} == set(ids)


def test_public_list_orders_newest_published_first_and_validates_paging(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    category = make_category(content_client, headers)
    first = create_post(content_client, headers, category_id=category["id"])
    second = create_post(content_client, headers, category_id=category["id"])
    content_client.post(f"{MANAGE}/posts/{first['id']}/publish", headers=headers)
    content_client.post(f"{MANAGE}/posts/{second['id']}/publish", headers=headers)
    listing = content_client.get(
        f"{BASE}/posts", params={"category": category["slug"]}
    ).json()
    assert [p["id"] for p in listing["data"]] == [second["id"], first["id"]]
    assert content_client.get(f"{BASE}/posts", params={"limit": 101}).status_code == 422
    assert content_client.get(f"{BASE}/posts", params={"limit": 0}).status_code == 422
    assert content_client.get(f"{BASE}/posts", params={"skip": -1}).status_code == 422


def test_update_post_is_partial(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    post = create_post(
        content_client,
        headers,
        title="Original",
        excerpt="keep me?",
        seo_title="s",
        body=doc(para("body")),
    )
    response = content_client.put(
        f"{MANAGE}/posts/{post['id']}",
        headers=headers,
        json={"title": "Renamed", "excerpt": None},
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Renamed"
    assert updated["excerpt"] is None  # explicit null clears
    assert updated["seo_title"] == "s"  # untouched
    assert updated["body"]["content"][0]["content"][0]["text"] == "body"
    assert updated["slug"] == post["slug"]  # renaming keeps the URL stable
    assert updated["updated_at"] >= post["updated_at"]
    # null for a required field is ignored rather than wiping it
    kept = content_client.put(
        f"{MANAGE}/posts/{post['id']}",
        headers=headers,
        json={"title": None, "body": None, "tag_ids": None, "slug": None},
    ).json()
    assert kept["title"] == "Renamed"
    assert kept["body"] == updated["body"]


def test_unknown_post_is_404(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    missing = str(uuid.uuid4())
    assert (
        content_client.get(f"{MANAGE}/posts/{missing}", headers=headers).status_code
        == 404
    )
    assert (
        content_client.put(
            f"{MANAGE}/posts/{missing}", headers=headers, json={"title": "x"}
        ).status_code
        == 404
    )
    assert (
        content_client.post(
            f"{MANAGE}/posts/{missing}/publish", headers=headers
        ).status_code
        == 404
    )
    assert (
        content_client.delete(f"{MANAGE}/posts/{missing}", headers=headers).status_code
        == 404
    )
    assert content_client.get(f"{BASE}/posts/no-such-post").status_code == 404
    assert content_client.get(f"{BASE}/pages/no-such-page").status_code == 404
    assert (
        content_client.get(f"{MANAGE}/posts/not-a-uuid", headers=headers).status_code
        == 422
    )


def test_delete_post_keeps_its_images(
    content_client: TestClient,
    storage: FakeStorage,
    editor: tuple[User, Headers],
    db: Session,
) -> None:
    _, headers = editor
    image = make_image(content_client, storage, headers)
    post = create_post(content_client, headers, cover_file_id=image["id"])
    assert (
        content_client.delete(
            f"{MANAGE}/posts/{post['id']}", headers=headers
        ).status_code
        == 200
    )
    db.expire_all()
    assert db.get(File, uuid.UUID(image["id"])) is not None
    assert db.get(Post, uuid.UUID(post["id"])) is None


# --- slugs ---


def test_slug_generation_and_uniqueness(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    title = f"Same Title {random_lower_string()[:10]}"
    first = create_post(content_client, headers, title=title)
    second = create_post(content_client, headers, title=title)
    third = create_post(content_client, headers, title=title)
    base = first["slug"]
    assert base == title.lower().replace(" ", "-")
    assert second["slug"] == f"{base}-2"
    assert third["slug"] == f"{base}-3"


def test_non_ascii_title_gets_random_slug(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    a = create_post(content_client, headers, title="你好，世界")
    b = create_post(content_client, headers, title="你好，世界")
    for post in (a, b):
        assert len(post["slug"]) == 8
        assert post["slug"].isalnum()
        assert post["slug"].isascii()
    assert a["slug"] != b["slug"]


def test_user_supplied_slug_is_normalized_and_made_unique(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    stem = random_lower_string()[:10]
    first = create_post(content_client, headers, slug=f"  My Custom_Slug!! {stem} ")
    assert first["slug"] == f"my-custom-slug-{stem}"
    second = create_post(content_client, headers, slug=f"my-custom-slug-{stem}")
    assert second["slug"] == f"my-custom-slug-{stem}-2"
    non_ascii = create_post(content_client, headers, slug="日本語")
    assert len(non_ascii["slug"]) == 8


def test_update_slug(content_client: TestClient, editor: tuple[User, Headers]) -> None:
    _, headers = editor
    a = create_post(content_client, headers)
    b = create_post(content_client, headers)
    # Setting a post's slug to its own value keeps it (no "-2").
    same = content_client.put(
        f"{MANAGE}/posts/{a['id']}", headers=headers, json={"slug": a["slug"]}
    ).json()
    assert same["slug"] == a["slug"]
    # Taking another post's slug gets a suffix.
    clash = content_client.put(
        f"{MANAGE}/posts/{b['id']}", headers=headers, json={"slug": a["slug"].upper()}
    ).json()
    assert clash["slug"] == f"{a['slug']}-2"
    # A slug is addressable publicly once published.
    new = content_client.put(
        f"{MANAGE}/posts/{b['id']}",
        headers=headers,
        json={"slug": f"fresh-{a['slug']}"},
    ).json()
    content_client.post(f"{MANAGE}/posts/{b['id']}/publish", headers=headers)
    assert content_client.get(f"{BASE}/posts/{new['slug']}").status_code == 200
    assert content_client.get(f"{BASE}/posts/{clash['slug']}").status_code == 404


def test_slug_race_becomes_409(
    content_client: TestClient,
    editor: tuple[User, Headers],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = editor
    existing = create_post(content_client, headers)
    # Simulate losing a race: the uniqueness lookup says "free" but the index disagrees.
    monkeypatch.setattr(service, "make_slug", lambda *a, **k: existing["slug"])
    response = content_client.post(
        f"{MANAGE}/posts", headers=headers, json={"title": "Racer"}
    )
    assert response.status_code == 409


def test_slug_rules_apply_to_categories_and_tags(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    name = f"News {random_lower_string()[:10]}"
    c1 = make_category(content_client, headers, name=name)
    c2 = make_category(content_client, headers, name=name)
    assert c2["slug"] == f"{c1['slug']}-2"
    t1 = make_tag(content_client, headers, name=name)
    t2 = make_tag(content_client, headers, name=name, slug="Custom Tag!")
    assert t1["slug"] == c1["slug"]  # separate tables, separate namespaces
    assert t2["slug"].startswith("custom-tag")
    assert len(make_tag(content_client, headers, name="标签")["slug"]) == 8


# --- body validation through the API ---


def test_body_roundtrip_and_resolved_image_src(
    content_client: TestClient,
    storage: FakeStorage,
    editor: tuple[User, Headers],
    make_user: MakeUser,
) -> None:
    _, headers = editor
    # The image belongs to someone else: any editor may reuse public images.
    _, other_headers = make_user(UserRole.editor)
    image = make_image(content_client, storage, other_headers)
    body = doc(
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Hi"}],
        },
        {
            "type": "image",
            "attrs": {
                "fileId": image["id"],
                "alt": "pic",
                # The client's src is ignored, never trusted or stored.
                "src": "https://evil.example/x.png",
            },
        },
    )
    post = create_post(content_client, headers, body=body)
    expected_src = f"{settings.API_V1_STR}/files/{image['id']}/content"
    image_node = post["body"]["content"][1]
    assert image_node["attrs"] == {
        "fileId": image["id"],
        "alt": "pic",
        "src": expected_src,
    }
    assert "evil.example" not in str(post)

    stored = content_client.get(f"{MANAGE}/posts/{post['id']}", headers=headers).json()
    assert stored["body"] == post["body"]
    content_client.post(f"{MANAGE}/posts/{post['id']}/publish", headers=headers)
    public = content_client.get(f"{BASE}/posts/{post['slug']}").json()
    assert public["body"]["content"][1]["attrs"]["src"] == expected_src


def test_stored_body_has_no_src(
    content_client: TestClient,
    storage: FakeStorage,
    editor: tuple[User, Headers],
    db: Session,
) -> None:
    _, headers = editor
    image = make_image(content_client, storage, headers)
    post = create_post(
        content_client,
        headers,
        body=doc({"type": "image", "attrs": {"fileId": image["id"], "src": "x"}}),
    )
    db.expire_all()
    row = db.get(Post, uuid.UUID(post["id"]))
    assert row is not None
    assert row.body["content"][0]["attrs"] == {"fileId": image["id"]}  # type: ignore[index] # test reads a dict tree


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        (doc({"type": "script", "content": []}), "unknown node type 'script'"),
        (
            doc(
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "x",
                            "marks": [
                                {
                                    "type": "link",
                                    "attrs": {"href": "javascript:alert(1)"},
                                }
                            ],
                        }
                    ],
                }
            ),
            "link href must start with",
        ),
        (
            doc(
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "x",
                            "marks": [
                                {
                                    "type": "link",
                                    "attrs": {"href": " JavaScript:alert(1)"},
                                }
                            ],
                        }
                    ],
                }
            ),
            "link href must start with",
        ),
        (
            doc({"type": "image", "attrs": {"src": "https://evil.example/x.png"}}),
            "image needs attrs.fileId",
        ),
        ({"type": "paragraph"}, "root node must have type 'doc'"),
    ],
)
def test_invalid_bodies_are_rejected(
    content_client: TestClient,
    editor: tuple[User, Headers],
    body: dict[str, Any],
    fragment: str,
) -> None:
    _, headers = editor
    r = content_client.post(
        f"{MANAGE}/posts", headers=headers, json={"title": "Bad", "body": body}
    )
    assert r.status_code == 422
    assert fragment in r.json()["detail"]
    # same rules on update and for pages
    post = create_post(content_client, headers)
    r = content_client.put(
        f"{MANAGE}/posts/{post['id']}", headers=headers, json={"body": body}
    )
    assert r.status_code == 422
    r = content_client.post(
        f"{MANAGE}/pages", headers=headers, json={"title": "Bad", "body": body}
    )
    assert r.status_code == 422


def test_body_over_one_megabyte_is_rejected(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    body = doc(*[para("x" * 90_000) for _ in range(12)])
    r = content_client.post(
        f"{MANAGE}/posts", headers=headers, json={"title": "Big", "body": body}
    )
    assert r.status_code == 422
    assert "too large" in r.json()["detail"]


def test_image_must_be_ready_public_image(
    content_client: TestClient,
    storage: FakeStorage,
    editor: tuple[User, Headers],
    db: Session,
) -> None:
    _, headers = editor

    def attempt(file_id: str) -> Any:  # noqa: ANN401
        # Any: returns the raw httpx response.
        return content_client.post(
            f"{MANAGE}/posts",
            headers=headers,
            json={
                "title": "Img",
                "body": doc({"type": "image", "attrs": {"fileId": file_id}}),
            },
        )

    # unknown file
    r = attempt(str(uuid.uuid4()))
    assert r.status_code == 422
    assert "not found" in r.json()["detail"]
    # private image
    private = make_image(content_client, storage, headers, public=False)
    r = attempt(private["id"])
    assert r.status_code == 422
    assert "public" in r.json()["detail"]
    # pending upload (never confirmed)
    ticket = content_client.post(
        f"{settings.API_V1_STR}/files/",
        headers=headers,
        json={
            "filename": "p.png",
            "content_type": "image/png",
            "size": 10,
            "public": True,
        },
    ).json()
    assert attempt(ticket["file"]["id"]).status_code == 422
    # not an inline image type, even if somehow public
    pdf = upload_ready(content_client, storage, headers)
    row = db.get(File, uuid.UUID(pdf["id"]))
    assert row is not None
    row.public = True
    db.add(row)
    db.commit()
    assert attempt(pdf["id"]).status_code == 422
    # a good one
    good = make_image(content_client, storage, headers)
    assert attempt(good["id"]).status_code == 200


def test_cover_image(
    content_client: TestClient,
    storage: FakeStorage,
    editor: tuple[User, Headers],
    make_user: MakeUser,
) -> None:
    _, headers = editor
    owner, owner_headers = make_user(UserRole.member)
    image = make_image(content_client, storage, owner_headers)
    post = create_post(content_client, headers, cover_file_id=image["id"])
    expected = f"{settings.API_V1_STR}/files/{image['id']}/content"
    assert post["cover_file_id"] == image["id"]
    assert post["cover_url"] == expected

    private = make_image(content_client, storage, owner_headers, public=False)
    bad = content_client.put(
        f"{MANAGE}/posts/{post['id']}",
        headers=headers,
        json={"cover_file_id": private["id"]},
    )
    assert bad.status_code == 422
    missing = content_client.put(
        f"{MANAGE}/posts/{post['id']}",
        headers=headers,
        json={"cover_file_id": str(uuid.uuid4())},
    )
    assert missing.status_code == 422

    # Deleting the file un-sets the cover (ON DELETE SET NULL); the post stays.
    removed = content_client.delete(
        f"{settings.API_V1_STR}/files/{image['id']}", headers=owner_headers
    )
    assert removed.status_code == 200
    after = content_client.get(f"{MANAGE}/posts/{post['id']}", headers=headers).json()
    assert after["cover_file_id"] is None
    assert after["cover_url"] is None

    # Explicit null clears a cover.
    other = make_image(content_client, storage, owner_headers)
    with_cover = content_client.put(
        f"{MANAGE}/posts/{post['id']}",
        headers=headers,
        json={"cover_file_id": other["id"]},
    ).json()
    assert with_cover["cover_url"] is not None
    cleared = content_client.put(
        f"{MANAGE}/posts/{post['id']}", headers=headers, json={"cover_file_id": None}
    ).json()
    assert cleared["cover_file_id"] is None


# --- categories and tags ---


def test_category_crud_and_public_listing(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    category = make_category(content_client, headers, description="About things")
    assert category["description"] == "About things"
    listed = content_client.get(f"{BASE}/categories").json()
    assert category["id"] in [c["id"] for c in listed["data"]]
    assert listed["count"] == len(listed["data"])

    renamed = content_client.put(
        f"{MANAGE}/categories/{category['id']}",
        headers=headers,
        json={"name": "Renamed", "slug": "Renamed Cat", "description": None},
    ).json()
    assert renamed["name"] == "Renamed"
    assert renamed["slug"].startswith("renamed-cat")
    assert renamed["description"] is None
    missing = str(uuid.uuid4())
    assert (
        content_client.put(
            f"{MANAGE}/categories/{missing}", headers=headers, json={"name": "x"}
        ).status_code
        == 404
    )
    assert (
        content_client.delete(
            f"{MANAGE}/categories/{missing}", headers=headers
        ).status_code
        == 404
    )


def test_tag_crud_and_public_listing(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    tag = make_tag(content_client, headers)
    listed = content_client.get(f"{BASE}/tags").json()
    assert tag["id"] in [t["id"] for t in listed["data"]]
    renamed = content_client.put(
        f"{MANAGE}/tags/{tag['id']}",
        headers=headers,
        json={"name": "Renamed tag", "slug": "tag-renamed"},
    ).json()
    assert renamed["name"] == "Renamed tag"
    assert renamed["slug"].startswith("tag-renamed")
    missing = str(uuid.uuid4())
    assert (
        content_client.put(
            f"{MANAGE}/tags/{missing}", headers=headers, json={"name": "x"}
        ).status_code
        == 404
    )
    assert (
        content_client.delete(f"{MANAGE}/tags/{missing}", headers=headers).status_code
        == 404
    )
    assert (
        content_client.delete(f"{MANAGE}/tags/{tag['id']}", headers=headers).status_code
        == 200
    )


def test_category_and_tag_filters_on_public_list(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    cat_a, cat_b = (make_category(content_client, headers) for _ in range(2))
    tag_x, tag_y = (make_tag(content_client, headers) for _ in range(2))
    p1 = create_post(
        content_client,
        headers,
        category_id=cat_a["id"],
        tag_ids=[tag_x["id"], tag_y["id"]],
    )
    p2 = create_post(
        content_client, headers, category_id=cat_b["id"], tag_ids=[tag_x["id"]]
    )
    p3 = create_post(content_client, headers, category_id=cat_a["id"])
    draft = create_post(
        content_client, headers, category_id=cat_a["id"], tag_ids=[tag_x["id"]]
    )
    for post in (p1, p2, p3):
        content_client.post(f"{MANAGE}/posts/{post['id']}/publish", headers=headers)

    def ids(**params: str) -> set[str]:
        data = content_client.get(f"{BASE}/posts", params=params).json()
        return {p["id"] for p in data["data"]}

    assert ids(category=cat_a["slug"]) == {p1["id"], p3["id"]}
    assert ids(category=cat_b["slug"]) == {p2["id"]}
    assert ids(tag=tag_x["slug"]) == {p1["id"], p2["id"]}
    assert ids(tag=tag_y["slug"]) == {p1["id"]}
    assert ids(category=cat_a["slug"], tag=tag_x["slug"]) == {p1["id"]}
    assert ids(category="no-such-category") == set()
    assert draft["id"] not in ids(tag=tag_x["slug"])

    full = content_client.get(f"{BASE}/posts/{p1['slug']}").json()
    assert full["category"]["slug"] == cat_a["slug"]
    assert {t["slug"] for t in full["tags"]} == {tag_x["slug"], tag_y["slug"]}


def test_post_category_and_tags_validation_and_update(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    tag_a, tag_b = (make_tag(content_client, headers) for _ in range(2))
    category = make_category(content_client, headers)
    bad_tag = content_client.post(
        f"{MANAGE}/posts",
        headers=headers,
        json={"title": "x", "tag_ids": [str(uuid.uuid4())]},
    )
    assert bad_tag.status_code == 422
    bad_cat = content_client.post(
        f"{MANAGE}/posts",
        headers=headers,
        json={"title": "x", "category_id": str(uuid.uuid4())},
    )
    assert bad_cat.status_code == 422

    post = create_post(
        content_client,
        headers,
        tag_ids=[tag_a["id"], tag_a["id"]],
        category_id=category["id"],
    )
    assert [t["id"] for t in post["tags"]] == [tag_a["id"]]  # duplicates collapse
    updated = content_client.put(
        f"{MANAGE}/posts/{post['id']}", headers=headers, json={"tag_ids": [tag_b["id"]]}
    ).json()
    assert [t["id"] for t in updated["tags"]] == [tag_b["id"]]
    assert updated["category"]["id"] == category["id"]
    cleared = content_client.put(
        f"{MANAGE}/posts/{post['id']}",
        headers=headers,
        json={"tag_ids": [], "category_id": None},
    ).json()
    assert cleared["tags"] == []
    assert cleared["category"] is None
    invalid = content_client.put(
        f"{MANAGE}/posts/{post['id']}",
        headers=headers,
        json={"category_id": str(uuid.uuid4())},
    )
    assert invalid.status_code == 422


def test_deleting_category_unsets_it_on_posts(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    category = make_category(content_client, headers)
    post = create_post(content_client, headers, category_id=category["id"])
    r = content_client.delete(f"{MANAGE}/categories/{category['id']}", headers=headers)
    assert r.status_code == 200
    after = content_client.get(f"{MANAGE}/posts/{post['id']}", headers=headers).json()
    assert after["category"] is None


def test_deleting_tag_removes_it_from_posts(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    keep, drop = (make_tag(content_client, headers) for _ in range(2))
    post = create_post(content_client, headers, tag_ids=[keep["id"], drop["id"]])
    r = content_client.delete(f"{MANAGE}/tags/{drop['id']}", headers=headers)
    assert r.status_code == 200
    after = content_client.get(f"{MANAGE}/posts/{post['id']}", headers=headers).json()
    assert [t["id"] for t in after["tags"]] == [keep["id"]]


def test_deleting_author_keeps_post(
    content_client: TestClient, make_user: MakeUser, db: Session
) -> None:
    author, headers = make_user(UserRole.editor)
    post = create_post(content_client, headers)
    assert post["author_id"] == str(author.id)
    db.delete(author)
    db.commit()
    _, other = make_user(UserRole.editor)
    after = content_client.get(f"{MANAGE}/posts/{post['id']}", headers=other).json()
    assert after["author_id"] is None
    assert after["author_name"] is None


def test_author_name_is_exposed(
    content_client: TestClient, make_user: MakeUser, db: Session
) -> None:
    author, headers = make_user(UserRole.editor)
    author.full_name = "Ada Lovelace"
    db.add(author)
    db.commit()
    post = create_post(content_client, headers)
    content_client.post(f"{MANAGE}/posts/{post['id']}/publish", headers=headers)
    public = content_client.get(f"{BASE}/posts/{post['slug']}").json()
    assert public["author_name"] == "Ada Lovelace"


# --- pages ---


def test_page_lifecycle(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    page = create_page(
        content_client,
        headers,
        title="About Us",
        body=doc(para("who we are")),
        seo_title="About",
        seo_description="desc",
    )
    assert page["status"] == "draft"
    assert page["slug"].startswith("about-us")
    assert content_client.get(f"{BASE}/pages/{page['slug']}").status_code == 404

    published = content_client.post(
        f"{MANAGE}/pages/{page['id']}/publish", headers=headers
    ).json()
    assert published["status"] == "published"
    assert published["published_at"] is not None
    public = content_client.get(f"{BASE}/pages/{page['slug']}")
    assert public.status_code == 200
    assert public.json()["body"]["content"][0]["content"][0]["text"] == "who we are"
    assert public.json()["seo_title"] == "About"
    # a post slug does not resolve as a page and vice versa
    assert content_client.get(f"{BASE}/posts/{page['slug']}").status_code == 404

    updated = content_client.put(
        f"{MANAGE}/pages/{page['id']}",
        headers=headers,
        json={
            "title": "About",
            "slug": "About Page",
            "seo_title": None,
            "body": doc(para("new text")),
        },
    ).json()
    assert updated["title"] == "About"
    assert updated["slug"].startswith("about-page")
    assert updated["seo_title"] is None
    assert updated["body"]["content"][0]["content"][0]["text"] == "new text"
    assert updated["seo_description"] == "desc"

    drafted = content_client.post(
        f"{MANAGE}/pages/{page['id']}/unpublish", headers=headers
    ).json()
    assert drafted["status"] == "draft"
    assert content_client.get(f"{BASE}/pages/{updated['slug']}").status_code == 404
    assert (
        content_client.get(f"{MANAGE}/pages/{page['id']}", headers=headers).status_code
        == 200
    )
    assert (
        content_client.delete(
            f"{MANAGE}/pages/{page['id']}", headers=headers
        ).status_code
        == 200
    )
    assert (
        content_client.get(f"{MANAGE}/pages/{page['id']}", headers=headers).status_code
        == 404
    )


def test_page_list_filters_and_unknown_ids(
    content_client: TestClient, editor: tuple[User, Headers], db: Session
) -> None:
    _, headers = editor
    stem = random_lower_string()[:10]
    a = create_page(content_client, headers, title=f"Alpha {stem}")
    b = create_page(content_client, headers, title=f"Beta {stem}")
    content_client.post(f"{MANAGE}/pages/{b['id']}/publish", headers=headers)
    found = content_client.get(
        f"{MANAGE}/pages", headers=headers, params={"q": stem}
    ).json()
    assert [p["id"] for p in found["data"]] == [a["id"], b["id"]]  # by title
    assert "body" not in found["data"][0]
    only_published = content_client.get(
        f"{MANAGE}/pages", headers=headers, params={"q": stem, "status": "published"}
    ).json()
    assert [p["id"] for p in only_published["data"]] == [b["id"]]
    missing = str(uuid.uuid4())
    assert (
        content_client.put(
            f"{MANAGE}/pages/{missing}", headers=headers, json={"title": "x"}
        ).status_code
        == 404
    )
    assert (
        content_client.delete(f"{MANAGE}/pages/{missing}", headers=headers).status_code
        == 404
    )
    assert db.get(Page, uuid.UUID(a["id"])) is not None


def test_page_slugs_are_independent_from_post_slugs(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    title = unique_title("Shared")
    post = create_post(content_client, headers, title=title)
    page = create_page(content_client, headers, title=title)
    assert post["slug"] == page["slug"]
    second_page = create_page(content_client, headers, title=title)
    assert second_page["slug"] == f"{page['slug']}-2"


def test_public_page_list_shows_published_pages_only(
    content_client: TestClient, editor: tuple[User, Headers]
) -> None:
    _, headers = editor
    published = create_page(
        content_client, headers, title="Zz Public Menu Page", body=doc(para("x"))
    )
    content_client.post(f"{MANAGE}/pages/{published['id']}/publish", headers=headers)
    draft = create_page(
        content_client, headers, title="Zz Draft Menu Page", body=doc(para("y"))
    )

    r = content_client.get(f"{BASE}/pages", params={"limit": 100})  # no auth needed
    assert r.status_code == 200
    items = r.json()["data"]
    slugs = {p["slug"] for p in items}
    assert published["slug"] in slugs
    assert draft["slug"] not in slugs
    assert all(p["status"] == "published" for p in items)
    assert "body" not in items[0]
    assert r.json()["count"] >= 1
    assert content_client.get(f"{BASE}/pages", params={"limit": 101}).status_code == 422

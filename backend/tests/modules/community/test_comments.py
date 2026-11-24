"""Comments: targets, validation, threading, edit window, delete, listing."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.db import engine
from app.core.roles import UserRole
from app.models import File, User
from app.modules.community.events import CommunityEvent, CommunityEventType
from app.modules.community.models import Comment
from app.modules.content import service as content_service
from tests.modules.community.conftest import Clock, MakePage, MakePost
from tests.modules.community.helpers import (
    BASE,
    add_comment,
    list_comments,
)
from tests.utils.files import MakeUser, upload_ready
from tests.utils.storage import FakeStorage

# --- who can comment ---


@pytest.mark.parametrize(
    "role,superuser",
    [
        (UserRole.member, False),
        (UserRole.editor, False),
        (UserRole.moderator, False),
        (UserRole.admin, False),
        (UserRole.member, True),
    ],
)
def test_every_logged_in_user_can_comment(
    cclient: TestClient,
    make_user: MakeUser,
    make_post: MakePost,
    role: UserRole,
    superuser: bool,
) -> None:
    _, headers = make_user(role, superuser=superuser)
    post = make_post()
    comment = add_comment(cclient, headers, post.id)
    assert comment["state"] == "visible"
    assert comment["body"] == "A thoughtful comment"
    assert comment["can_edit"] is True


def test_anonymous_can_read_but_not_write(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, headers = make_user()
    post = make_post()
    comment = add_comment(cclient, headers, post.id)
    public = list_comments(cclient, post.id)
    assert [c["id"] for c in public["data"]] == [comment["id"]]
    assert public["data"][0]["liked_by_me"] is False
    assert public["data"][0]["can_edit"] is False
    url = f"{BASE}/posts/{post.id}/comments"
    assert cclient.post(url, json={"body": "hi"}).status_code == 401
    assert (
        cclient.put(f"{BASE}/comments/{comment['id']}", json={"body": "x"}).status_code
        == 401
    )
    assert cclient.delete(f"{BASE}/comments/{comment['id']}").status_code == 401
    assert cclient.put(f"{BASE}/comments/{comment['id']}/like").status_code == 401
    assert (
        cclient.post(
            f"{BASE}/comments/{comment['id']}/report", json={"reason": "spam"}
        ).status_code
        == 401
    )


def test_stale_token_is_treated_as_anonymous_on_public_reads(
    cclient: TestClient, make_post: MakePost
) -> None:
    post = make_post()
    response = cclient.get(
        f"{BASE}/posts/{post.id}/comments",
        headers={"Authorization": "Bearer not-a-token"},
    )
    assert response.status_code == 200


# --- targets ---


def test_comments_only_on_published_targets(
    cclient: TestClient,
    make_user: MakeUser,
    make_post: MakePost,
    make_page: MakePage,
) -> None:
    _, headers = make_user()
    draft_post = make_post(published=False)
    draft_page = make_page(published=False)
    for kind, target in (("posts", draft_post.id), ("pages", draft_page.id)):
        url = f"{BASE}/{kind}/{target}/comments"
        assert (
            cclient.post(url, headers=headers, json={"body": "hi"}).status_code == 404
        )
        assert cclient.get(url).status_code == 404
    missing = uuid.uuid4()
    assert (
        cclient.post(
            f"{BASE}/posts/{missing}/comments", headers=headers, json={"body": "hi"}
        ).status_code
        == 404
    )


def test_page_comments_work_like_post_comments(
    cclient: TestClient, make_user: MakeUser, make_page: MakePage
) -> None:
    _, headers = make_user()
    page = make_page()
    comment = add_comment(cclient, headers, page.id, kind="pages")
    assert comment["target_type"] == "page"
    assert comment["target_id"] == str(page.id)
    listed = list_comments(cclient, page.id, kind="pages")
    assert listed["count"] == 1
    assert listed["post_like_count"] is None


def test_unpublished_post_hides_comments_and_republish_restores_them(
    cclient: TestClient, db: Session, make_user: MakeUser, make_post: MakePost
) -> None:
    _, headers = make_user()
    post = make_post()
    comment = add_comment(cclient, headers, post.id)
    content_service.set_status(session=db, item=post, status="draft")
    assert cclient.get(f"{BASE}/posts/{post.id}/comments").status_code == 404
    # Nothing can be done with the comment while the post is a draft.
    like = cclient.put(f"{BASE}/comments/{comment['id']}/like", headers=headers)
    assert like.status_code == 404
    edit = cclient.put(
        f"{BASE}/comments/{comment['id']}", headers=headers, json={"body": "new"}
    )
    assert edit.status_code == 404
    reply = cclient.post(
        f"{BASE}/posts/{post.id}/comments",
        headers=headers,
        json={"body": "reply", "parent_id": comment["id"]},
    )
    assert reply.status_code == 404
    content_service.set_status(session=db, item=post, status="published")
    assert list_comments(cclient, post.id)["count"] == 1


def test_deleting_a_post_deletes_its_comments(
    cclient: TestClient, db: Session, make_user: MakeUser, make_post: MakePost
) -> None:
    _, headers = make_user()
    post = make_post()
    top = add_comment(cclient, headers, post.id)
    add_comment(cclient, headers, post.id, parent_id=top["id"])
    ids = [uuid.UUID(top["id"])]
    content_service.delete_item(session=db, item=post)
    db.expire_all()
    left = db.exec(select(Comment).where(col(Comment.post_id) == post.id)).all()
    assert left == []
    assert db.get(Comment, ids[0]) is None


# --- body validation ---


@pytest.mark.parametrize(
    "body",
    [
        "",
        "   \n\t ",
        "x" * 5001,
        "null\x00byte",
        "bell\x07",
        "escape\x1b[0m",
        "del\x7f",
    ],
)
def test_invalid_bodies_are_rejected(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost, body: str
) -> None:
    _, headers = make_user()
    post = make_post()
    response = cclient.post(
        f"{BASE}/posts/{post.id}/comments", headers=headers, json={"body": body}
    )
    assert response.status_code == 422, body


def test_body_is_trimmed_and_stored_as_plain_text(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, headers = make_user()
    post = make_post()
    comment = add_comment(
        cclient, headers, post.id, body="  <b>bold</b> & more\r\nsecond\tline \n"
    )
    assert comment["body"] == "<b>bold</b> & more\nsecond\tline"
    assert add_comment(cclient, headers, post.id, body="x" * 5000)["body"] == "x" * 5000


def test_report_note_validation(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    author, a_headers = make_user()
    _, headers = make_user()
    post = make_post()
    comment = add_comment(cclient, a_headers, post.id)
    url = f"{BASE}/comments/{comment['id']}/report"
    assert cclient.post(url, headers=headers, json={"reason": "x"}).status_code == 422
    bad = cclient.post(url, headers=headers, json={"reason": "other", "note": "a\x00b"})
    assert bad.status_code == 422
    ok = cclient.post(url, headers=headers, json={"reason": "other", "note": "  "})
    assert ok.status_code == 200


# --- threading ---


def test_reply_one_level_only(
    cclient: TestClient,
    make_user: MakeUser,
    make_post: MakePost,
    emitted: list[CommunityEvent],
) -> None:
    author, a_headers = make_user()
    _, b_headers = make_user()
    post = make_post()
    top = add_comment(cclient, a_headers, post.id)
    reply = add_comment(cclient, b_headers, post.id, body="reply", parent_id=top["id"])
    assert reply["parent_id"] == top["id"]
    nested = cclient.post(
        f"{BASE}/posts/{post.id}/comments",
        headers=a_headers,
        json={"body": "nope", "parent_id": reply["id"]},
    )
    assert nested.status_code == 400
    assert "reply to a reply" in nested.json()["detail"]
    # The parent must belong to the same target.
    other = make_post()
    wrong = cclient.post(
        f"{BASE}/posts/{other.id}/comments",
        headers=a_headers,
        json={"body": "nope", "parent_id": top["id"]},
    )
    assert wrong.status_code == 404
    unknown = cclient.post(
        f"{BASE}/posts/{post.id}/comments",
        headers=a_headers,
        json={"body": "nope", "parent_id": str(uuid.uuid4())},
    )
    assert unknown.status_code == 404
    listed = list_comments(cclient, post.id)
    assert listed["count"] == 1
    assert [r["id"] for r in listed["data"][0]["replies"]] == [reply["id"]]
    assert [e.type for e in emitted] == [CommunityEventType.comment_replied]
    assert emitted[0].recipient_id == author.id


def test_replying_to_yourself_emits_no_event(
    cclient: TestClient,
    make_user: MakeUser,
    make_post: MakePost,
    emitted: list[CommunityEvent],
) -> None:
    _, headers = make_user()
    post = make_post()
    top = add_comment(cclient, headers, post.id)
    add_comment(cclient, headers, post.id, parent_id=top["id"])
    assert emitted == []


# --- edit ---


def test_edit_within_window_by_author_only(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost, clock: Clock
) -> None:
    _, headers = make_user()
    _, other = make_user()
    post = make_post()
    comment = add_comment(cclient, headers, post.id)
    url = f"{BASE}/comments/{comment['id']}"
    clock.advance(minutes=14, seconds=50)
    edited = cclient.put(url, headers=headers, json={"body": "  edited  "})
    assert edited.status_code == 200
    assert edited.json()["body"] == "edited"
    assert edited.json()["edited_at"] is not None
    assert cclient.put(url, headers=other, json={"body": "mine now"}).status_code == 403
    clock.advance(minutes=1)
    late = cclient.put(url, headers=headers, json={"body": "too late"})
    assert late.status_code == 403
    assert "15 minutes" in late.json()["detail"]
    listed = list_comments(cclient, post.id, headers)
    assert listed["data"][0]["body"] == "edited"
    assert listed["data"][0]["can_edit"] is False


def test_moderators_cannot_edit_other_peoples_comments(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, headers = make_user()
    _, mod = make_user(UserRole.moderator)
    post = make_post()
    comment = add_comment(cclient, headers, post.id)
    response = cclient.put(
        f"{BASE}/comments/{comment['id']}", headers=mod, json={"body": "edit"}
    )
    assert response.status_code == 403


# --- delete ---


def test_author_deletes_comment_without_replies_for_real(
    cclient: TestClient, db: Session, make_user: MakeUser, make_post: MakePost
) -> None:
    _, headers = make_user()
    _, other = make_user()
    post = make_post()
    comment = add_comment(cclient, headers, post.id)
    url = f"{BASE}/comments/{comment['id']}"
    assert cclient.delete(url, headers=other).status_code == 403
    assert cclient.delete(url, headers=headers).status_code == 200
    db.expire_all()
    assert db.get(Comment, uuid.UUID(comment["id"])) is None
    assert list_comments(cclient, post.id)["count"] == 0
    assert cclient.delete(url, headers=headers).status_code == 404


def test_author_delete_with_replies_leaves_a_placeholder(
    cclient: TestClient, db: Session, make_user: MakeUser, make_post: MakePost
) -> None:
    _, headers = make_user()
    _, other = make_user()
    post = make_post()
    top = add_comment(cclient, headers, post.id, body="secret words")
    reply = add_comment(cclient, other, post.id, body="reply", parent_id=top["id"])
    assert (
        cclient.delete(f"{BASE}/comments/{top['id']}", headers=headers).status_code
        == 200
    )
    stored = db.exec(
        select(Comment).where(col(Comment.id) == uuid.UUID(top["id"]))
    ).one()
    db.refresh(stored)
    assert stored.body == "[deleted]"
    listed = list_comments(cclient, post.id)["data"]
    assert listed[0]["state"] == "deleted"
    assert listed[0]["body"] == "[deleted]"
    assert listed[0]["author"] is None
    assert [r["id"] for r in listed[0]["replies"]] == [reply["id"]]
    # A deleted comment can't be edited, liked or replied to.
    assert (
        cclient.put(
            f"{BASE}/comments/{top['id']}", headers=headers, json={"body": "x"}
        ).status_code
        == 404
    )
    assert (
        cclient.put(f"{BASE}/comments/{top['id']}/like", headers=other).status_code
        == 404
    )
    again = cclient.post(
        f"{BASE}/posts/{post.id}/comments",
        headers=other,
        json={"body": "hello?", "parent_id": top["id"]},
    )
    assert again.status_code == 400
    # Once the last reply is gone the placeholder disappears from the list.
    assert (
        cclient.delete(f"{BASE}/comments/{reply['id']}", headers=other).status_code
        == 200
    )
    assert list_comments(cclient, post.id)["count"] == 0


# --- listing ---


def test_sort_and_pagination_of_top_level_comments(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost, clock: Clock
) -> None:
    _, headers = make_user(superuser=True)
    post = make_post()
    ids = []
    for index in range(3):
        ids.append(add_comment(cclient, headers, post.id, body=f"c{index}")["id"])
        clock.advance(minutes=1)
    reply = add_comment(cclient, headers, post.id, body="r", parent_id=ids[0])
    newest = list_comments(cclient, post.id, sort="newest")
    assert [c["id"] for c in newest["data"]] == ids[::-1]
    assert newest["count"] == 3  # replies are not counted
    oldest = list_comments(cclient, post.id, sort="oldest")
    assert [c["id"] for c in oldest["data"]] == ids
    page = list_comments(cclient, post.id, sort="oldest", skip=1, limit=1)
    assert [c["id"] for c in page["data"]] == [ids[1]]
    assert page["count"] == 3
    assert (
        list_comments(cclient, post.id, sort="oldest")["data"][0]["replies"][0]["id"]
        == reply["id"]
    )


def test_authors_show_a_name_and_avatar_but_never_an_email(
    cclient: TestClient,
    db: Session,
    storage: FakeStorage,
    make_user: MakeUser,
    make_post: MakePost,
) -> None:
    named, named_headers = make_user()
    named.full_name = "Ada Lovelace"
    unnamed, unnamed_headers = make_user()
    db.add(named)
    db.commit()
    file = upload_ready(
        cclient,
        storage,
        named_headers,
        size=500,
        content_type="image/png",
        filename="a.png",
        public=True,
    )
    cclient.put(
        f"{settings.API_V1_STR}/users/me/avatar",
        headers=named_headers,
        json={"file_id": file["id"]},
    )
    post = make_post()
    first = add_comment(cclient, named_headers, post.id)
    add_comment(cclient, unnamed_headers, post.id, parent_id=first["id"])
    add_comment(cclient, unnamed_headers, post.id)
    listed = list_comments(cclient, post.id, named_headers)
    raw = cclient.get(f"{BASE}/posts/{post.id}/comments").text
    for user in (named, unnamed):
        assert user.email not in raw
        assert user.email not in str(listed)
    authors = {c["author"]["id"]: c["author"] for c in listed["data"]}
    assert authors[str(named.id)]["display_name"] == "Ada Lovelace"
    assert authors[str(named.id)]["avatar_url"]
    assert authors[str(unnamed.id)]["display_name"] == f"Member {str(unnamed.id)[:8]}"
    assert authors[str(unnamed.id)]["avatar_url"] is None
    assert set(authors[str(named.id)]) == {
        "id",
        "username",
        "display_name",
        "avatar_url",
    }
    own = db.get(File, uuid.UUID(file["id"]))
    assert own is not None


def test_listing_uses_a_constant_number_of_queries(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, headers = make_user(superuser=True)
    post = make_post()
    first = add_comment(cclient, headers, post.id)

    def count_queries() -> int:
        statements: list[str] = []

        def record(*args: object) -> None:
            statements.append("q")

        event.listen(engine, "before_cursor_execute", record)
        try:
            list_comments(cclient, post.id, headers)
        finally:
            event.remove(engine, "before_cursor_execute", record)
        return len(statements)

    few = count_queries()
    for index in range(6):
        other, other_headers = make_user()
        top = add_comment(cclient, other_headers, post.id, body=f"c{index}")
        add_comment(cclient, other_headers, post.id, parent_id=first["id"])
        add_comment(cclient, headers, post.id, parent_id=top["id"])
    assert count_queries() == few


def test_users_can_be_deleted_and_their_comments_remain(
    cclient: TestClient, db: Session, make_user: MakeUser, make_post: MakePost
) -> None:
    user, headers = make_user()
    post = make_post()
    comment = add_comment(cclient, headers, post.id)
    reply_to = add_comment(cclient, headers, post.id, body="second")
    db.delete(db.get(User, user.id))
    db.commit()
    listed = list_comments(cclient, post.id)["data"]
    assert {c["id"] for c in listed} == {comment["id"], reply_to["id"]}
    assert all(c["author"] is None for c in listed)


# --- rate limit ---


def test_comment_rate_limit(
    cclient: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    make_user: MakeUser,
    make_post: MakePost,
    clock: Clock,
) -> None:
    monkeypatch.setattr(settings, "COMMENTS_PER_USER_PER_HOUR", 2)
    _, headers = make_user()
    _, other = make_user()
    _, superuser = make_user(superuser=True)
    post = make_post()
    add_comment(cclient, headers, post.id)
    add_comment(cclient, headers, post.id)
    blocked = cclient.post(
        f"{BASE}/posts/{post.id}/comments", headers=headers, json={"body": "third"}
    )
    assert blocked.status_code == 429
    # Per user, and superusers are exempt.
    add_comment(cclient, other, post.id)
    for _ in range(3):
        add_comment(cclient, superuser, post.id)
    # The window slides.
    clock.advance(minutes=61)
    add_comment(cclient, headers, post.id)

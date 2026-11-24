"""Notifications: created by the right events, listing, unread count, read, cleanup."""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.core.roles import UserRole
from app.models import User
from app.modules.community import notifications as notification_service
from app.modules.community import service
from app.modules.community.events import (
    CommunityEvent,
    CommunityEventType,
    emit,
)
from app.modules.community.models import Notification, NotificationType
from app.modules.content import service as content_service
from app.scripts import cleanup_notifications
from tests.modules.community.conftest import Clock, MakePost
from tests.modules.community.helpers import BASE, MOD, add_comment
from tests.utils.files import Headers, MakeUser

NOTIFICATIONS = f"{BASE}/notifications"


def inbox(client: TestClient, headers: Headers, **params: Any) -> dict[str, Any]:
    response = client.get(NOTIFICATIONS, headers=headers, params=params)
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


def unread(client: TestClient, headers: Headers) -> int:
    response = client.get(f"{NOTIFICATIONS}/unread-count", headers=headers)
    assert response.status_code == 200
    count: int = response.json()["unread_count"]
    return count


def like(client: TestClient, headers: Headers, comment_id: str) -> None:
    assert (
        client.put(f"{BASE}/comments/{comment_id}/like", headers=headers).status_code
        == 200
    )


def unlike(client: TestClient, headers: Headers, comment_id: str) -> None:
    assert (
        client.delete(f"{BASE}/comments/{comment_id}/like", headers=headers).status_code
        == 200
    )


# --- one test per type ---


def test_reply_notifies_the_parent_author(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    author, author_headers = make_user()
    replier, replier_headers = make_user()
    post = make_post()
    parent = add_comment(cclient, author_headers, post.id, body="Parent")
    reply = add_comment(
        cclient,
        replier_headers,
        post.id,
        body="A  reply\nwith lines",
        parent_id=parent["id"],
    )
    items = inbox(cclient, author_headers)["data"]
    assert len(items) == 1
    item = items[0]
    assert item["type"] == "comment_replied"
    assert item["actor"]["username"] == replier.username
    assert item["comment_id"] == reply["id"]
    assert item["comment_snippet"] == "A reply with lines"
    assert item["target"] == {
        "type": "post",
        "id": str(post.id),
        "title": post.title,
        "slug": post.slug,
    }
    assert item["read"] is False
    assert replier.email not in str(items)
    assert inbox(cclient, replier_headers)["count"] == 0


def test_reply_on_a_page_links_to_the_page(
    cclient: TestClient, db: Session, make_user: MakeUser
) -> None:
    from app.modules.content.schemas import PageCreate

    author, author_headers = make_user()
    _, replier_headers = make_user()
    page = content_service.create_page(
        session=db, user=author, data=PageCreate(title="About us")
    )
    page = content_service.set_status(session=db, item=page, status="published")
    parent = add_comment(cclient, author_headers, page.id, kind="pages")
    add_comment(cclient, replier_headers, page.id, kind="pages", parent_id=parent["id"])
    target = inbox(cclient, author_headers)["data"][0]["target"]
    assert target["type"] == "page"
    assert target["slug"] == page.slug


def test_no_notification_for_replying_to_yourself(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, headers = make_user()
    post = make_post()
    parent = add_comment(cclient, headers, post.id)
    add_comment(cclient, headers, post.id, parent_id=parent["id"])
    assert inbox(cclient, headers)["count"] == 0


def test_like_notifies_and_collapses_while_unread(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    author, author_headers = make_user()
    fan, fan_headers = make_user()
    other, other_headers = make_user()
    post = make_post()
    comment = add_comment(cclient, author_headers, post.id, body="Nice words")
    like(cclient, fan_headers, comment["id"])
    like(cclient, fan_headers, comment["id"])  # idempotent
    unlike(cclient, fan_headers, comment["id"])
    like(cclient, fan_headers, comment["id"])  # again, still unread: collapsed
    first = inbox(cclient, author_headers)
    assert first["count"] == 1
    assert first["data"][0]["type"] == "comment_liked"
    assert first["data"][0]["actor"]["username"] == fan.username
    assert first["data"][0]["comment_snippet"] == "Nice words"
    # another person's like is a new notification
    like(cclient, other_headers, comment["id"])
    assert inbox(cclient, author_headers)["count"] == 2
    # once read, the same person liking again is news again
    cclient.post(f"{NOTIFICATIONS}/read-all", headers=author_headers)
    unlike(cclient, fan_headers, comment["id"])
    like(cclient, fan_headers, comment["id"])
    assert inbox(cclient, author_headers)["count"] == 3
    assert unread(cclient, author_headers) == 1
    assert other.username  # the second liker exists


def test_unlike_does_not_delete_the_notification(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, author_headers = make_user()
    _, fan_headers = make_user()
    comment = add_comment(cclient, author_headers, make_post().id)
    like(cclient, fan_headers, comment["id"])
    unlike(cclient, fan_headers, comment["id"])
    assert inbox(cclient, author_headers)["count"] == 1


def test_no_notification_for_liking_your_own_comment(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, headers = make_user()
    comment = add_comment(cclient, headers, make_post().id)
    like(cclient, headers, comment["id"])
    assert inbox(cclient, headers)["count"] == 0


def test_follow_notifies_and_collapses_while_unread(
    cclient: TestClient, make_user: MakeUser
) -> None:
    target, target_headers = make_user()
    fan, fan_headers = make_user()
    cclient.put(f"{BASE}/users/{target.username}/follow", headers=fan_headers)
    cclient.put(f"{BASE}/users/{target.username}/follow", headers=fan_headers)
    cclient.delete(f"{BASE}/users/{target.username}/follow", headers=fan_headers)
    cclient.put(f"{BASE}/users/{target.username}/follow", headers=fan_headers)
    data = inbox(cclient, target_headers)
    assert data["count"] == 1
    item = data["data"][0]
    assert item["type"] == "new_follower"
    assert item["actor"]["username"] == fan.username
    assert item["comment_id"] is None
    assert item["comment_snippet"] is None
    assert item["target"] is None
    # the one who follows hears nothing
    assert inbox(cclient, fan_headers)["count"] == 0


def test_hide_and_moderator_delete_notify_the_author_not_restore(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    author, author_headers = make_user()
    _, moderator = make_user(UserRole.moderator)
    post = make_post()
    hidden = add_comment(cclient, author_headers, post.id, body="Spicy take")
    deleted = add_comment(cclient, author_headers, post.id, body="Worse take")
    cclient.post(f"{MOD}/comments/{hidden['id']}/hide", headers=moderator)
    cclient.post(f"{MOD}/comments/{hidden['id']}/restore", headers=moderator)
    assert inbox(cclient, author_headers)["count"] == 1
    response = cclient.delete(f"{MOD}/comments/{deleted['id']}", headers=moderator)
    assert response.status_code == 200
    data = inbox(cclient, author_headers)
    assert data["count"] == 2
    assert {i["type"] for i in data["data"]} == {"comment_moderated"}
    by_comment = {i["comment_id"]: i for i in data["data"]}
    # the first one still links to the (restored) comment; the really deleted one lost it
    assert hidden["id"] in by_comment
    assert by_comment[hidden["id"]]["comment_snippet"] == "Spicy take"
    assert None in by_comment
    assert by_comment[None]["target"]["slug"] == post.slug
    assert by_comment[None]["actor"]["username"]
    assert author.username


def test_moderating_your_own_comment_notifies_nobody(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, moderator = make_user(UserRole.moderator)
    comment = add_comment(cclient, moderator, make_post().id)
    cclient.post(f"{MOD}/comments/{comment['id']}/hide", headers=moderator)
    assert inbox(cclient, moderator)["count"] == 0


# --- content of the notification ---


def test_snippet_is_at_most_140_characters(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, author_headers = make_user()
    _, fan_headers = make_user()
    comment = add_comment(cclient, author_headers, make_post().id, body="word " * 100)
    like(cclient, fan_headers, comment["id"])
    snippet = inbox(cclient, author_headers)["data"][0]["comment_snippet"]
    assert len(snippet) == 140
    assert snippet.endswith("…")


def test_a_hidden_reply_does_not_leak_its_text_to_the_recipient(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, author_headers = make_user()
    _, replier_headers = make_user()
    _, moderator = make_user(UserRole.moderator)
    post = make_post()
    parent = add_comment(cclient, author_headers, post.id)
    reply = add_comment(
        cclient, replier_headers, post.id, body="Rude words", parent_id=parent["id"]
    )
    cclient.post(f"{MOD}/comments/{reply['id']}/hide", headers=moderator)
    item = inbox(cclient, author_headers)["data"][0]
    assert item["type"] == "comment_replied"
    assert item["comment_snippet"] is None
    assert "Rude" not in str(item)
    # the replier is told about the moderation, with their own text
    own = inbox(cclient, replier_headers)["data"][0]
    assert own["type"] == "comment_moderated"
    assert own["comment_snippet"] == "Rude words"


def test_unpublished_post_has_no_link_and_deleted_post_keeps_the_row(
    cclient: TestClient, db: Session, make_user: MakeUser, make_post: MakePost
) -> None:
    _, author_headers = make_user()
    _, fan_headers = make_user()
    post = make_post()
    comment = add_comment(cclient, author_headers, post.id)
    like(cclient, fan_headers, comment["id"])
    assert inbox(cclient, author_headers)["data"][0]["target"] is not None
    content_service.set_status(session=db, item=post, status="draft")
    assert inbox(cclient, author_headers)["data"][0]["target"] is None
    db.delete(post)
    db.commit()
    data = inbox(cclient, author_headers)
    assert data["count"] == 1
    assert data["data"][0]["target"] is None
    assert data["data"][0]["comment_id"] is None  # the comment went with the post


def test_deleted_actor_leaves_a_notification_without_actor(
    cclient: TestClient, db: Session, make_user: MakeUser
) -> None:
    target, target_headers = make_user()
    fan, fan_headers = make_user()
    cclient.put(f"{BASE}/users/{target.username}/follow", headers=fan_headers)
    row = db.get(User, fan.id)
    assert row is not None
    db.delete(row)
    db.commit()
    item = inbox(cclient, target_headers)["data"][0]
    assert item["type"] == "new_follower"
    assert item["actor"] is None


def test_newest_first_and_pagination(
    cclient: TestClient, make_user: MakeUser, clock: Clock
) -> None:
    target, target_headers = make_user()
    fans = []
    for _ in range(3):
        fan = make_user()
        fans.append(fan)
        cclient.put(f"{BASE}/users/{target.username}/follow", headers=fan[1])
        clock.advance(seconds=5)
    data = inbox(cclient, target_headers)
    assert [i["actor"]["username"] for i in data["data"]] == [
        f[0].username for f in reversed(fans)
    ]
    page = inbox(cclient, target_headers, skip=1, limit=1)
    assert page["count"] == 3
    assert [i["actor"]["username"] for i in page["data"]] == [fans[1][0].username]
    assert (
        cclient.get(
            NOTIFICATIONS, params={"limit": 0}, headers=target_headers
        ).status_code
        == 422
    )


# --- unread, read, read-all, ownership ---


def test_unread_read_and_read_all(
    cclient: TestClient, make_user: MakeUser, clock: Clock
) -> None:
    target, target_headers = make_user()
    for _ in range(3):
        _, headers = make_user()
        cclient.put(f"{BASE}/users/{target.username}/follow", headers=headers)
        clock.advance(seconds=1)
    assert unread(cclient, target_headers) == 3
    items = inbox(cclient, target_headers)["data"]
    first_id = items[0]["id"]
    response = cclient.post(f"{NOTIFICATIONS}/{first_id}/read", headers=target_headers)
    assert response.status_code == 200
    assert response.json() == {"unread_count": 2}
    again = cclient.post(f"{NOTIFICATIONS}/{first_id}/read", headers=target_headers)
    assert again.json() == {"unread_count": 2}  # idempotent
    after = inbox(cclient, target_headers)["data"]
    assert [i["read"] for i in after] == [True, False, False]
    done = cclient.post(f"{NOTIFICATIONS}/read-all", headers=target_headers)
    assert done.json() == {"unread_count": 0}
    assert unread(cclient, target_headers) == 0
    assert all(i["read"] for i in inbox(cclient, target_headers)["data"])
    assert inbox(cclient, target_headers)["count"] == 3  # read ones stay


def test_notifications_are_private(cclient: TestClient, make_user: MakeUser) -> None:
    owner, owner_headers = make_user()
    _, fan_headers = make_user()
    _, snoop_headers = make_user()
    cclient.put(f"{BASE}/users/{owner.username}/follow", headers=fan_headers)
    notification_id = inbox(cclient, owner_headers)["data"][0]["id"]
    # someone else's id -> 404, same as an unknown one, and nothing changes
    for other in (snoop_headers, fan_headers):
        response = cclient.post(
            f"{NOTIFICATIONS}/{notification_id}/read", headers=other
        )
        assert response.status_code == 404
    unknown = cclient.post(
        f"{NOTIFICATIONS}/{uuid.uuid4()}/read", headers=owner_headers
    )
    assert unknown.status_code == 404
    assert unread(cclient, owner_headers) == 1
    assert inbox(cclient, snoop_headers)["count"] == 0
    # read-all of the snoop leaves mine alone
    cclient.post(f"{NOTIFICATIONS}/read-all", headers=snoop_headers)
    assert unread(cclient, owner_headers) == 1
    # login required
    for method, url in (
        ("get", NOTIFICATIONS),
        ("get", f"{NOTIFICATIONS}/unread-count"),
        ("post", f"{NOTIFICATIONS}/read-all"),
        ("post", f"{NOTIFICATIONS}/{notification_id}/read"),
    ):
        assert cclient.request(method, url).status_code == 401, url


# --- robustness ---


def test_a_failing_handler_never_breaks_the_request(
    cclient: TestClient,
    make_user: MakeUser,
    make_post: MakePost,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(session: Session, event: CommunityEvent) -> None:
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(notification_service, "handle_event", boom)
    _, author_headers = make_user()
    _, fan_headers = make_user()
    comment = add_comment(cclient, author_headers, make_post().id)
    response = cclient.put(f"{BASE}/comments/{comment['id']}/like", headers=fan_headers)
    assert response.status_code == 200
    assert inbox(cclient, author_headers)["count"] == 0


def test_events_without_a_valid_recipient_are_ignored(
    db: Session, make_user: MakeUser
) -> None:
    actor, _ = make_user()
    nobody = CommunityEvent(
        type=CommunityEventType.user_followed, actor_id=actor.id, recipient_id=None
    )
    assert notification_service.handle_event(db, nobody) is None
    gone = CommunityEvent(
        type=CommunityEventType.user_followed,
        actor_id=actor.id,
        recipient_id=uuid.uuid4(),
    )
    assert notification_service.handle_event(db, gone) is None
    emit(gone)  # through the public hook, own session: still nothing, no error
    count = db.exec(
        select(Notification).where(col(Notification.actor_id) == actor.id)
    ).all()
    assert count == []


def test_follow_emits_a_user_followed_event(
    cclient: TestClient, make_user: MakeUser, emitted: list[CommunityEvent]
) -> None:
    target, _ = make_user()
    fan, fan_headers = make_user()
    cclient.put(f"{BASE}/users/{target.username}/follow", headers=fan_headers)
    cclient.put(f"{BASE}/users/{target.username}/follow", headers=fan_headers)
    assert [(e.type, e.actor_id, e.recipient_id) for e in emitted] == [
        (CommunityEventType.user_followed, fan.id, target.id)
    ]


# --- cleanup ---


def test_cleanup_deletes_notifications_older_than_90_days(
    db: Session, make_user: MakeUser
) -> None:
    recipient, _ = make_user()
    actor, _ = make_user()
    now = service.now()

    def add(days: int) -> uuid.UUID:
        row = Notification(
            recipient_id=recipient.id,
            type=NotificationType.new_follower,
            actor_id=actor.id,
            created_at=now - timedelta(days=days),
        )
        db.add(row)
        db.commit()
        return row.id

    old, almost, fresh = add(91), add(89), add(0)
    removed = notification_service.cleanup_old_notifications(session=db)
    assert removed >= 1
    left = {n.id for n in db.exec(select(Notification)).all()}
    assert old not in left
    assert almost in left
    assert fresh in left


def test_cleanup_command_runs(db: Session, make_user: MakeUser) -> None:
    recipient, _ = make_user()
    row = Notification(
        recipient_id=recipient.id,
        type=NotificationType.new_follower,
        created_at=service.now() - timedelta(days=200),
    )
    db.add(row)
    db.commit()
    row_id = row.id
    assert cleanup_notifications.main() >= 1
    db.expire_all()
    assert db.get(Notification, row_id) is None
    assert cleanup_notifications.main() == 0

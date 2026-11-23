"""Moderation (queue, hide/restore/delete, resolve) and suspensions."""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.roles import UserRole
from app.modules.community import service
from app.modules.community.events import CommunityEvent, CommunityEventType
from app.modules.community.models import Comment
from tests.modules.community.conftest import Clock, MakePost
from tests.modules.community.helpers import (
    BASE,
    MOD,
    add_comment,
    list_comments,
    queue,
    report,
)
from tests.utils.files import MakeUser

# --- who may moderate ---


def test_moderation_permission_matrix(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, author = make_user()
    post = make_post()
    comment = add_comment(cclient, author, post.id)
    cid = comment["id"]
    endpoints: list[tuple[str, str, dict[str, Any] | None]] = [
        ("get", f"{MOD}/comments", None),
        ("post", f"{MOD}/comments/{cid}/resolve-reports", None),
        ("get", f"{MOD}/suspensions", None),
        ("post", f"{MOD}/suspensions", {"user_id": str(uuid.uuid4())}),
    ]
    # anonymous -> 401
    for method, url, body in endpoints:
        assert cclient.request(method, url, json=body).status_code == 401, url
    # member and editor (a sibling of moderator, not a parent) -> 403
    for role in (UserRole.member, UserRole.editor):
        _, headers = make_user(role)
        for method, url, body in endpoints:
            response = cclient.request(method, url, headers=headers, json=body)
            assert response.status_code == 403, (role, url)
        for method, url in (
            ("post", f"{MOD}/comments/{cid}/hide"),
            ("post", f"{MOD}/comments/{cid}/restore"),
            ("delete", f"{MOD}/comments/{cid}"),
            ("delete", f"{MOD}/suspensions/{uuid.uuid4()}"),
        ):
            assert cclient.request(method, url, headers=headers).status_code == 403
    # moderator, admin and superuser pass
    for role, superuser in (
        (UserRole.moderator, False),
        (UserRole.admin, False),
        (UserRole.member, True),
    ):
        _, headers = make_user(role, superuser=superuser)
        assert cclient.get(f"{MOD}/comments", headers=headers).status_code == 200
        assert cclient.get(f"{MOD}/suspensions", headers=headers).status_code == 200
        hidden = cclient.post(f"{MOD}/comments/{cid}/hide", headers=headers)
        assert hidden.status_code == 200
        restored = cclient.post(f"{MOD}/comments/{cid}/restore", headers=headers)
        assert restored.status_code == 200
    assert (
        cclient.post(f"{MOD}/comments/{uuid.uuid4()}/hide", headers=headers).status_code
        == 404
    )


# --- hide / restore ---


def test_hidden_comments_leave_public_lists_unless_they_have_visible_replies(
    cclient: TestClient,
    make_user: MakeUser,
    make_post: MakePost,
    emitted: list[CommunityEvent],
) -> None:
    author, a_headers = make_user()
    _, b_headers = make_user()
    _, mod = make_user(UserRole.moderator)
    post = make_post()
    lonely = add_comment(cclient, a_headers, post.id, body="lonely")
    parent = add_comment(cclient, a_headers, post.id, body="parent text")
    reply = add_comment(
        cclient, b_headers, post.id, body="reply", parent_id=parent["id"]
    )

    for cid in (lonely["id"], parent["id"]):
        assert (
            cclient.post(f"{MOD}/comments/{cid}/hide", headers=mod).status_code == 200
        )
    # Hiding twice changes nothing and notifies once.
    cclient.post(f"{MOD}/comments/{lonely['id']}/hide", headers=mod)
    assert [e.type for e in emitted if e.type == CommunityEventType.comment_hidden] == [
        CommunityEventType.comment_hidden
    ] * 2
    assert emitted[0].recipient_id == author.id

    listed = list_comments(cclient, post.id)["data"]
    assert [c["id"] for c in listed] == [parent["id"]]
    placeholder = listed[0]
    assert placeholder["state"] == "hidden"
    assert placeholder["body"] == "[removed by a moderator]"
    assert placeholder["author"] is None
    assert "parent text" not in str(placeholder)
    assert [r["id"] for r in placeholder["replies"]] == [reply["id"]]
    # The author sees the placeholder too and can no longer edit it.
    own = list_comments(cclient, post.id, a_headers)["data"][0]
    assert own["body"] == "[removed by a moderator]"
    assert own["can_edit"] is False

    # Hidden comments are in the queue with their real body.
    hidden = {c["id"]: c for c in queue(cclient, mod, filter="hidden")}
    assert hidden[lonely["id"]]["state"] == "hidden"
    assert hidden[parent["id"]]["body"] == "parent text"

    # Hiding a reply removes it completely.
    assert (
        cclient.post(f"{MOD}/comments/{reply['id']}/hide", headers=mod).status_code
        == 200
    )
    assert list_comments(cclient, post.id)["count"] == 0

    for cid in (lonely["id"], parent["id"], reply["id"]):
        assert (
            cclient.post(f"{MOD}/comments/{cid}/restore", headers=mod).status_code
            == 200
        )
    restored = list_comments(cclient, post.id, sort="oldest")
    assert [c["id"] for c in restored["data"]] == [lonely["id"], parent["id"]]
    assert restored["data"][1]["body"] == "parent text"
    assert len(restored["data"][1]["replies"]) == 1
    still_hidden = {c["id"] for c in queue(cclient, mod, filter="hidden")}
    assert not still_hidden & {lonely["id"], parent["id"], reply["id"]}


def test_a_deleted_comment_cannot_be_hidden_or_restored(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, a_headers = make_user()
    _, b_headers = make_user()
    _, mod = make_user(UserRole.moderator)
    post = make_post()
    parent = add_comment(cclient, a_headers, post.id)
    add_comment(cclient, b_headers, post.id, parent_id=parent["id"])
    cclient.delete(f"{BASE}/comments/{parent['id']}", headers=a_headers)
    assert (
        cclient.post(f"{MOD}/comments/{parent['id']}/hide", headers=mod).status_code
        == 400
    )
    assert (
        cclient.post(f"{MOD}/comments/{parent['id']}/restore", headers=mod).status_code
        == 400
    )


# --- moderator delete ---


def test_moderator_delete_without_replies_is_a_real_delete(
    cclient: TestClient,
    db: Session,
    make_user: MakeUser,
    make_post: MakePost,
    emitted: list[CommunityEvent],
) -> None:
    author, a_headers = make_user()
    _, r_headers = make_user()
    _, mod = make_user(UserRole.moderator)
    post = make_post()
    comment = add_comment(cclient, a_headers, post.id)
    report(cclient, r_headers, comment["id"])
    assert (
        cclient.delete(f"{MOD}/comments/{comment['id']}", headers=mod).status_code
        == 200
    )
    db.expire_all()
    assert db.get(Comment, uuid.UUID(comment["id"])) is None
    assert list_comments(cclient, post.id)["count"] == 0
    assert all(c["id"] != comment["id"] for c in queue(cclient, mod))
    event = emitted[-1]
    assert event.type == CommunityEventType.comment_deleted_by_moderator
    assert event.recipient_id == author.id
    assert event.target_type == "post"
    assert event.target_id == post.id
    assert (
        cclient.delete(f"{MOD}/comments/{comment['id']}", headers=mod).status_code
        == 404
    )


def test_moderator_delete_with_replies_leaves_a_removed_placeholder(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, a_headers = make_user()
    _, b_headers = make_user()
    _, c_headers = make_user()
    _, mod = make_user(UserRole.moderator)
    post = make_post()
    parent = add_comment(cclient, a_headers, post.id, body="nasty words")
    add_comment(cclient, b_headers, post.id, parent_id=parent["id"])
    report(cclient, c_headers, parent["id"])
    assert (
        cclient.delete(f"{MOD}/comments/{parent['id']}", headers=mod).status_code == 200
    )
    top = list_comments(cclient, post.id)["data"][0]
    assert top["state"] == "removed"
    assert top["body"] == "[removed by a moderator]"
    assert "nasty" not in str(top)
    # Nothing left to moderate: the report was closed, the comment left the queue.
    assert all(c["id"] != parent["id"] for c in queue(cclient, mod))
    assert len(top["replies"]) == 1


# --- queue ---


def test_queue_filters_and_pagination(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, a_headers = make_user()
    _, r_headers = make_user()
    _, mod = make_user(UserRole.moderator)
    post = make_post()
    reported = add_comment(cclient, a_headers, post.id)
    hidden = add_comment(cclient, a_headers, post.id)
    clean = add_comment(cclient, a_headers, post.id)
    report(cclient, r_headers, reported["id"], "other")
    cclient.post(f"{MOD}/comments/{hidden['id']}/hide", headers=mod)

    def ids(**params: Any) -> set[str]:
        return {c["id"] for c in queue(cclient, mod, **params)}

    assert {reported["id"], hidden["id"]} <= ids()
    assert clean["id"] not in ids()
    assert reported["id"] in ids(filter="reported")
    assert hidden["id"] not in ids(filter="reported")
    assert hidden["id"] in ids(filter="hidden")
    assert reported["id"] not in ids(filter="hidden")
    response = cclient.get(f"{MOD}/comments", headers=mod, params={"limit": 1})
    assert len(response.json()["data"]) == 1
    assert response.json()["count"] >= 2
    assert (
        cclient.get(f"{MOD}/comments", headers=mod, params={"filter": "x"}).status_code
        == 422
    )


# --- moderators can't act on admin / superuser content ---


@pytest.mark.parametrize(
    "role,superuser",
    [(UserRole.admin, False), (UserRole.member, True)],
)
def test_moderators_cannot_moderate_admins_or_superusers(
    cclient: TestClient,
    make_user: MakeUser,
    make_post: MakePost,
    role: UserRole,
    superuser: bool,
) -> None:
    protected, p_headers = make_user(role, superuser=superuser)
    _, mod = make_user(UserRole.moderator)
    _, other_admin = make_user(UserRole.admin)
    _, root = make_user(superuser=True)
    post = make_post()
    comment = add_comment(cclient, p_headers, post.id)
    cid = comment["id"]
    for headers in (mod, other_admin):
        for method, url in (
            ("post", f"{MOD}/comments/{cid}/hide"),
            ("post", f"{MOD}/comments/{cid}/restore"),
            ("post", f"{MOD}/comments/{cid}/resolve-reports"),
            ("delete", f"{MOD}/comments/{cid}"),
        ):
            assert cclient.request(method, url, headers=headers).status_code == 403, url
        suspend = cclient.post(
            f"{MOD}/suspensions", headers=headers, json={"user_id": str(protected.id)}
        )
        assert suspend.status_code == 403
    # The comment is untouched, and a superuser can act.
    assert list_comments(cclient, post.id)["count"] == 1
    assert cclient.post(f"{MOD}/comments/{cid}/hide", headers=root).status_code == 200
    assert (
        cclient.post(f"{MOD}/comments/{cid}/restore", headers=root).status_code == 200
    )
    ok = cclient.post(
        f"{MOD}/suspensions", headers=root, json={"user_id": str(protected.id)}
    )
    assert ok.status_code == 200
    # Ending it is covered by the same rule.
    assert (
        cclient.delete(f"{MOD}/suspensions/{ok.json()['id']}", headers=mod).status_code
        == 403
    )
    assert (
        cclient.delete(f"{MOD}/suspensions/{ok.json()['id']}", headers=root).status_code
        == 200
    )


def test_moderators_can_moderate_editors_moderators_and_members(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, mod = make_user(UserRole.moderator)
    post = make_post()
    for role in (UserRole.member, UserRole.editor, UserRole.moderator):
        _, headers = make_user(role)
        comment = add_comment(cclient, headers, post.id)
        assert (
            cclient.post(
                f"{MOD}/comments/{comment['id']}/hide", headers=mod
            ).status_code
            == 200
        )


# --- suspensions ---


def suspend(
    client: TestClient, headers: dict[str, str], user_id: uuid.UUID, **extra: Any
) -> Any:
    return client.post(
        f"{MOD}/suspensions", headers=headers, json={"user_id": str(user_id), **extra}
    )


def test_suspended_members_get_403_on_participation_but_not_elsewhere(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    member, headers = make_user()
    _, other = make_user()
    _, mod = make_user(UserRole.moderator)
    post = make_post()
    mine = add_comment(cclient, headers, post.id)
    theirs = add_comment(cclient, other, post.id)
    assert cclient.get(f"{BASE}/me/suspension", headers=headers).json() == {
        "suspended": False,
        "until": None,
        "reason": None,
    }
    created = suspend(cclient, mod, member.id, reason="  spamming  ")
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["active"] is True
    assert body["reason"] == "spamming"
    assert body["user"]["display_name"].startswith("Member ")
    assert member.email not in created.text

    detail = "You are suspended from commenting"
    blocked = [
        cclient.post(
            f"{BASE}/posts/{post.id}/comments", headers=headers, json={"body": "hi"}
        ),
        cclient.put(
            f"{BASE}/comments/{mine['id']}", headers=headers, json={"body": "x"}
        ),
        cclient.put(f"{BASE}/comments/{theirs['id']}/like", headers=headers),
        cclient.put(f"{BASE}/posts/{post.id}/like", headers=headers),
        report(cclient, headers, theirs["id"]),
    ]
    for response in blocked:
        assert response.status_code == 403
        assert response.json()["detail"] == detail
    # Login and everything else keeps working; so does undoing your own actions.
    assert (
        cclient.get(f"{settings.API_V1_STR}/users/me", headers=headers).status_code
        == 200
    )
    assert (
        cclient.get(f"{BASE}/posts/{post.id}/comments", headers=headers).status_code
        == 200
    )
    assert (
        cclient.delete(
            f"{BASE}/comments/{theirs['id']}/like", headers=headers
        ).status_code
        == 200
    )
    assert (
        cclient.delete(f"{BASE}/posts/{post.id}/like", headers=headers).status_code
        == 200
    )
    mine_state = cclient.get(f"{BASE}/me/suspension", headers=headers).json()
    assert mine_state["suspended"] is True
    assert mine_state["reason"] == "spamming"
    assert (
        cclient.delete(f"{BASE}/comments/{mine['id']}", headers=headers).status_code
        == 200
    )

    # Other members are unaffected.
    add_comment(cclient, other, post.id)

    # Only one active suspension per user.
    assert suspend(cclient, mod, member.id).status_code == 409

    active = cclient.get(f"{MOD}/suspensions", headers=mod).json()
    assert body["id"] in {s["id"] for s in active["data"]}

    ended = cclient.delete(f"{MOD}/suspensions/{body['id']}", headers=mod)
    assert ended.status_code == 200
    assert ended.json()["active"] is False
    assert ended.json()["ended_at"] is not None
    assert (
        cclient.delete(f"{MOD}/suspensions/{body['id']}", headers=mod).json()["active"]
        is False
    )
    add_comment(cclient, headers, post.id)
    assert (
        cclient.get(f"{BASE}/me/suspension", headers=headers).json()["suspended"]
        is False
    )
    ids_active = {
        s["id"] for s in cclient.get(f"{MOD}/suspensions", headers=mod).json()["data"]
    }
    assert body["id"] not in ids_active
    history = cclient.get(
        f"{MOD}/suspensions", headers=mod, params={"active_only": False}
    )
    assert body["id"] in {s["id"] for s in history.json()["data"]}


def test_timed_suspension_expires(
    cclient: TestClient,
    db: Session,
    make_user: MakeUser,
    make_post: MakePost,
    clock: Clock,
) -> None:
    member, headers = make_user()
    _, mod = make_user(UserRole.moderator)
    post = make_post()
    until = service.now() + timedelta(hours=2)
    assert suspend(cclient, mod, member.id, until=until.isoformat()).status_code == 200
    assert (
        cclient.post(
            f"{BASE}/posts/{post.id}/comments", headers=headers, json={"body": "hi"}
        ).status_code
        == 403
    )
    clock.advance(hours=3)
    add_comment(cclient, headers, post.id)
    assert (
        cclient.get(f"{BASE}/me/suspension", headers=headers).json()["suspended"]
        is False
    )
    # An expired suspension no longer blocks a new one.
    assert suspend(cclient, mod, member.id).status_code == 200
    assert not db.is_modified(member)


def test_suspension_validation(cclient: TestClient, make_user: MakeUser) -> None:
    member, _ = make_user()
    mod_user, mod = make_user(UserRole.moderator)
    past = (service.now() - timedelta(hours=1)).isoformat()
    assert suspend(cclient, mod, member.id, until=past).status_code == 400
    assert suspend(cclient, mod, uuid.uuid4()).status_code == 404
    assert suspend(cclient, mod, mod_user.id).status_code == 400
    assert (
        cclient.delete(f"{MOD}/suspensions/{uuid.uuid4()}", headers=mod).status_code
        == 404
    )
    assert cclient.get(f"{BASE}/me/suspension").status_code == 401
    bad = cclient.get(f"{MOD}/suspensions", headers=mod, params={"limit": 0})
    assert bad.status_code == 422

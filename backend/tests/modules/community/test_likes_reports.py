"""Likes (comments and posts) and reports."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.roles import UserRole
from app.modules.community.events import CommunityEvent, CommunityEventType
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

# --- comment likes ---


def test_comment_like_is_idempotent_and_counted(
    cclient: TestClient,
    make_user: MakeUser,
    make_post: MakePost,
    emitted: list[CommunityEvent],
) -> None:
    author, a_headers = make_user()
    _, b_headers = make_user()
    _, c_headers = make_user()
    post = make_post()
    comment = add_comment(cclient, a_headers, post.id)
    url = f"{BASE}/comments/{comment['id']}/like"

    first = cclient.put(url, headers=b_headers)
    assert first.json() == {"like_count": 1, "liked_by_me": True}
    again = cclient.put(url, headers=b_headers)
    assert again.json() == {"like_count": 1, "liked_by_me": True}
    assert cclient.put(url, headers=c_headers).json()["like_count"] == 2

    # Only the first like of a user notifies the author.
    assert [e.type for e in emitted] == [CommunityEventType.comment_liked] * 2
    assert emitted[0].recipient_id == author.id

    listed = list_comments(cclient, post.id, b_headers)["data"][0]
    assert listed["like_count"] == 2
    assert listed["liked_by_me"] is True
    assert list_comments(cclient, post.id)["data"][0]["liked_by_me"] is False

    gone = cclient.delete(url, headers=b_headers)
    assert gone.json() == {"like_count": 1, "liked_by_me": False}
    assert cclient.delete(url, headers=b_headers).json()["like_count"] == 1
    assert cclient.delete(url, headers=a_headers).json()["like_count"] == 1


def test_liking_your_own_comment_does_not_notify(
    cclient: TestClient,
    make_user: MakeUser,
    make_post: MakePost,
    emitted: list[CommunityEvent],
) -> None:
    _, headers = make_user()
    post = make_post()
    comment = add_comment(cclient, headers, post.id)
    response = cclient.put(f"{BASE}/comments/{comment['id']}/like", headers=headers)
    assert response.json()["like_count"] == 1
    assert emitted == []


def test_cannot_like_unknown_or_hidden_comments(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, headers = make_user()
    _, mod = make_user(UserRole.moderator)
    post = make_post()
    comment = add_comment(cclient, headers, post.id)
    assert (
        cclient.put(f"{BASE}/comments/{uuid.uuid4()}/like", headers=headers).status_code
        == 404
    )
    cclient.post(f"{MOD}/comments/{comment['id']}/hide", headers=mod)
    assert (
        cclient.put(
            f"{BASE}/comments/{comment['id']}/like", headers=headers
        ).status_code
        == 404
    )
    assert (
        cclient.delete(
            f"{BASE}/comments/{uuid.uuid4()}/like", headers=headers
        ).status_code
        == 404
    )


# --- post likes ---


def test_post_like_is_idempotent_and_counted_outside_the_content_module(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, a_headers = make_user()
    _, b_headers = make_user()
    post = make_post()
    url = f"{BASE}/posts/{post.id}/like"
    assert cclient.get(url).json() == {"like_count": 0, "liked_by_me": False}
    assert cclient.put(url, headers=a_headers).json() == {
        "like_count": 1,
        "liked_by_me": True,
    }
    assert cclient.put(url, headers=a_headers).json()["like_count"] == 1
    assert cclient.put(url, headers=b_headers).json()["like_count"] == 2
    assert cclient.get(url, headers=a_headers).json() == {
        "like_count": 2,
        "liked_by_me": True,
    }
    listed = list_comments(cclient, post.id, a_headers)
    assert listed["post_like_count"] == 2
    assert listed["post_liked_by_me"] is True
    assert list_comments(cclient, post.id)["post_liked_by_me"] is False
    assert cclient.delete(url, headers=a_headers).json() == {
        "like_count": 1,
        "liked_by_me": False,
    }
    assert cclient.delete(url, headers=a_headers).json()["like_count"] == 1
    # The post itself has no like fields: the content module is unchanged.
    public = cclient.get(f"{settings.API_V1_STR}/content/posts/{post.slug}").json()
    assert "like_count" not in public


def test_post_likes_need_a_published_post(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, headers = make_user()
    draft = make_post(published=False)
    assert (
        cclient.put(f"{BASE}/posts/{draft.id}/like", headers=headers).status_code == 404
    )
    assert cclient.get(f"{BASE}/posts/{draft.id}/like").status_code == 404
    assert (
        cclient.put(f"{BASE}/posts/{uuid.uuid4()}/like", headers=headers).status_code
        == 404
    )
    assert (
        cclient.delete(f"{BASE}/posts/{uuid.uuid4()}/like", headers=headers).status_code
        == 404
    )
    assert cclient.put(f"{BASE}/posts/{draft.id}/like").status_code == 401


# --- reports ---


def test_report_once_per_user_and_shows_in_queue(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    author, a_headers = make_user()
    reporter, r_headers = make_user()
    _, other = make_user()
    _, mod = make_user(UserRole.moderator)
    post = make_post()
    comment = add_comment(cclient, a_headers, post.id, body="buy my pills")

    own = report(cclient, a_headers, comment["id"])
    assert own.status_code == 400
    assert report(cclient, r_headers, comment["id"], "abuse").status_code == 200
    again = report(cclient, r_headers, comment["id"], "spam")
    assert again.status_code == 409
    assert report(cclient, other, comment["id"], "other").status_code == 200
    assert report(cclient, r_headers, str(uuid.uuid4())).status_code == 404

    items = queue(cclient, mod)
    mine = next(i for i in items if i["id"] == comment["id"])
    assert mine["open_report_count"] == 2
    assert {r["reason"] for r in mine["reports"]} == {"abuse", "other"}
    assert mine["body"] == "buy my pills"
    assert mine["author"]["id"] == str(author.id)
    assert str(reporter.id) in {r["reporter"]["id"] for r in mine["reports"]}
    assert reporter.email not in cclient.get(f"{MOD}/comments", headers=mod).text

    # Resolving closes the reports, but the user still can't report it again.
    resolved = cclient.post(
        f"{MOD}/comments/{comment['id']}/resolve-reports", headers=mod
    )
    assert resolved.status_code == 200
    assert all(i["id"] != comment["id"] for i in queue(cclient, mod))
    assert report(cclient, r_headers, comment["id"]).status_code == 409


def test_only_visible_comments_can_be_reported(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    _, a_headers = make_user()
    _, r_headers = make_user()
    _, mod = make_user(UserRole.moderator)
    post = make_post()
    comment = add_comment(cclient, a_headers, post.id)
    cclient.post(f"{MOD}/comments/{comment['id']}/hide", headers=mod)
    assert report(cclient, r_headers, comment["id"]).status_code == 404


def test_report_rate_limit(
    cclient: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    make_user: MakeUser,
    make_post: MakePost,
    clock: Clock,
) -> None:
    monkeypatch.setattr(settings, "REPORTS_PER_USER_PER_DAY", 2)
    _, a_headers = make_user()
    _, r_headers = make_user()
    _, superuser = make_user(superuser=True)
    post = make_post()
    comments = [
        add_comment(cclient, a_headers, post.id, body=f"c{i}")["id"] for i in range(4)
    ]
    assert report(cclient, r_headers, comments[0]).status_code == 200
    assert report(cclient, r_headers, comments[1]).status_code == 200
    assert report(cclient, r_headers, comments[2]).status_code == 429
    for comment_id in comments[:3]:
        assert report(cclient, superuser, comment_id).status_code == 200
    clock.advance(hours=25)
    assert report(cclient, r_headers, comments[2]).status_code == 200

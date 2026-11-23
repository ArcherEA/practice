"""Public profiles, a member's comments, follows, followers/following and the feed."""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.core.roles import UserRole
from app.models import User
from app.modules.content import service as content_service
from tests.modules.community.conftest import MakePage, MakePost
from tests.modules.community.helpers import BASE, MOD, add_comment
from tests.utils.files import Headers, MakeUser


def profile(
    client: TestClient, username: str, headers: Headers | None = None
) -> dict[str, Any]:
    response = client.get(f"{BASE}/users/{username}", headers=headers)
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


def follow(client: TestClient, headers: Headers, username: str) -> Any:
    return client.put(f"{BASE}/users/{username}/follow", headers=headers)


def set_active(db: Session, user: User, active: bool) -> None:
    row = db.get(User, user.id)
    assert row is not None
    row.is_active = active
    db.add(row)
    db.commit()


# --- profile ---


def test_profile_is_public_case_insensitive_and_never_shows_the_email(
    cclient: TestClient, make_user: MakeUser
) -> None:
    user, headers = make_user()
    cclient.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"full_name": "Ada Lovelace", "bio": "Maths."},
    )
    data = profile(cclient, user.username.upper())  # anonymous
    assert data["username"] == user.username
    assert data["display_name"] == "Ada Lovelace"
    assert data["bio"] == "Maths."
    assert data["avatar_url"] is None
    assert data["joined_at"]
    assert data["comment_count"] == 0
    assert data["follower_count"] == 0
    assert data["following_count"] == 0
    assert data["followed_by_me"] is None
    assert data["is_suspended"] is None
    # never an email, and none of the private fields
    raw = cclient.get(f"{BASE}/users/{user.username}").text
    assert user.email not in raw
    assert "email" not in data
    assert "hashed_password" not in raw
    assert "is_active" not in data
    assert "role" not in data


def test_profile_falls_back_to_a_member_name(
    cclient: TestClient, make_user: MakeUser
) -> None:
    user, _ = make_user()
    assert profile(cclient, user.username)["display_name"] == (
        f"Member {str(user.id)[:8]}"
    )


def test_unknown_and_inactive_users_are_404(
    cclient: TestClient, db: Session, make_user: MakeUser
) -> None:
    user, _ = make_user()
    assert cclient.get(f"{BASE}/users/nobody_here_x").status_code == 404
    set_active(db, user, False)
    for path in ("", "/comments", "/followers", "/following"):
        assert cclient.get(f"{BASE}/users/{user.username}{path}").status_code == 404
    _, headers = make_user()
    assert follow(cclient, headers, user.username).status_code == 404
    set_active(db, user, True)
    assert cclient.get(f"{BASE}/users/{user.username}").status_code == 200


def test_is_suspended_is_only_for_moderators_and_above(
    cclient: TestClient, make_user: MakeUser
) -> None:
    target, target_headers = make_user()
    _, member = make_user()
    _, editor = make_user(UserRole.editor)
    moderator_user, moderator = make_user(UserRole.moderator)
    _, admin = make_user(UserRole.admin)
    assert profile(cclient, target.username, moderator)["is_suspended"] is False
    response = cclient.post(
        f"{MOD}/suspensions", headers=moderator, json={"user_id": str(target.id)}
    )
    assert response.status_code == 200, response.text
    assert profile(cclient, target.username, moderator)["is_suspended"] is True
    assert profile(cclient, target.username, admin)["is_suspended"] is True
    for headers in (None, member, editor, target_headers):
        shown = profile(cclient, target.username, headers)
        assert shown["is_suspended"] is None
    assert moderator_user.id != target.id


def test_counts_and_followed_by_me(cclient: TestClient, make_user: MakeUser) -> None:
    a, a_headers = make_user()
    b, b_headers = make_user()
    c, c_headers = make_user()
    follow(cclient, b_headers, a.username)
    follow(cclient, c_headers, a.username)
    follow(cclient, a_headers, b.username)
    seen = profile(cclient, a.username, b_headers)
    assert seen["follower_count"] == 2
    assert seen["following_count"] == 1
    assert seen["followed_by_me"] is True
    assert profile(cclient, a.username, a_headers)["followed_by_me"] is False
    assert profile(cclient, c.username, b_headers)["followed_by_me"] is False


# --- a member's comments ---


def test_profile_comments_only_show_visible_comments_on_published_content(
    cclient: TestClient,
    db: Session,
    make_user: MakeUser,
    make_post: MakePost,
    make_page: MakePage,
) -> None:
    user, headers = make_user()
    _, moderator = make_user(UserRole.moderator)
    visible_post = make_post()
    hidden_post = make_post()
    draft_post = make_post()
    page = make_page()
    first = add_comment(cclient, headers, visible_post.id, body="On the post")
    hidden = add_comment(cclient, headers, hidden_post.id, body="To be hidden")
    add_comment(cclient, headers, draft_post.id, body="Later a draft")
    on_page = add_comment(cclient, headers, page.id, body="On a page", kind="pages")
    cclient.post(f"{MOD}/comments/{hidden['id']}/hide", headers=moderator)
    content_service.set_status(session=db, item=draft_post, status="draft")

    assert profile(cclient, user.username)["comment_count"] == 2
    response = cclient.get(f"{BASE}/users/{user.username}/comments")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert [c["id"] for c in data["data"]] == [
        on_page["id"],
        first["id"],
    ]  # newest first
    by_id = {c["id"]: c for c in data["data"]}
    assert by_id[first["id"]]["target"] == {
        "type": "post",
        "id": str(visible_post.id),
        "title": visible_post.title,
        "slug": visible_post.slug,
    }
    assert by_id[on_page["id"]]["target"]["type"] == "page"
    assert by_id[on_page["id"]]["target"]["slug"] == page.slug
    assert by_id[first["id"]]["author"]["username"] == user.username
    assert user.email not in response.text

    paged = cclient.get(
        f"{BASE}/users/{user.username}/comments", params={"skip": 1, "limit": 1}
    ).json()
    assert paged["count"] == 2
    assert [c["id"] for c in paged["data"]] == [first["id"]]


def test_comment_authors_carry_a_username(
    cclient: TestClient, make_user: MakeUser, make_post: MakePost
) -> None:
    user, headers = make_user()
    post = make_post()
    comment = add_comment(cclient, headers, post.id)
    assert comment["author"]["username"] == user.username


# --- follows ---


def test_follow_rules(cclient: TestClient, make_user: MakeUser) -> None:
    a, a_headers = make_user()
    b, b_headers = make_user()
    assert cclient.put(f"{BASE}/users/{b.username}/follow").status_code == 401
    assert cclient.delete(f"{BASE}/users/{b.username}/follow").status_code == 401
    assert follow(cclient, a_headers, a.username).status_code == 400  # not yourself
    assert follow(cclient, a_headers, "no_such_user").status_code == 404
    first = follow(cclient, a_headers, b.username.upper())
    assert first.status_code == 200
    assert first.json() == {"following": True, "follower_count": 1}
    again = follow(cclient, a_headers, b.username)  # idempotent
    assert again.json() == {"following": True, "follower_count": 1}
    gone = cclient.delete(f"{BASE}/users/{b.username}/follow", headers=a_headers)
    assert gone.json() == {"following": False, "follower_count": 0}
    gone_again = cclient.delete(f"{BASE}/users/{b.username}/follow", headers=a_headers)
    assert gone_again.status_code == 200
    assert gone_again.json()["following"] is False
    assert b_headers  # b never did anything


def test_suspended_members_may_still_follow(
    cclient: TestClient, make_user: MakeUser
) -> None:
    suspended, headers = make_user()
    target, _ = make_user()
    _, moderator = make_user(UserRole.moderator)
    cclient.post(
        f"{MOD}/suspensions", headers=moderator, json={"user_id": str(suspended.id)}
    )
    assert follow(cclient, headers, target.username).status_code == 200


def test_followers_and_following_lists(
    cclient: TestClient, db: Session, make_user: MakeUser
) -> None:
    star, _ = make_user()
    fans = [make_user() for _ in range(3)]
    for _, headers in fans:
        assert follow(cclient, headers, star.username).status_code == 200
    # the star follows the first fan
    _, star_headers = make_user()
    star_row = star
    assert star_row.username
    listing = cclient.get(f"{BASE}/users/{star.username}/followers").json()
    assert listing["count"] == 3
    names = [a["username"] for a in listing["data"]]
    assert names == [u.username for u, _ in reversed(fans)]  # newest follow first
    assert all(
        set(a) == {"id", "username", "display_name", "avatar_url"}
        for a in listing["data"]
    )
    assert star.email not in str(listing)
    page = cclient.get(
        f"{BASE}/users/{star.username}/followers", params={"skip": 2, "limit": 5}
    ).json()
    assert page["count"] == 3
    assert [a["username"] for a in page["data"]] == [fans[0][0].username]
    # an inactive follower disappears from the lists and the count
    set_active(db, fans[1][0], False)
    shown = cclient.get(f"{BASE}/users/{star.username}/followers").json()
    assert shown["count"] == 2
    set_active(db, fans[1][0], True)
    # following
    follower, follower_headers = fans[0]
    other, _ = make_user()
    follow(cclient, follower_headers, other.username)
    following = cclient.get(f"{BASE}/users/{follower.username}/following").json()
    assert [a["username"] for a in following["data"]] == [
        other.username,
        star.username,
    ]
    assert following["count"] == 2
    assert star_headers


def test_following_activity_feed(
    cclient: TestClient,
    db: Session,
    make_user: MakeUser,
    make_post: MakePost,
) -> None:
    me, my_headers = make_user()
    friend, friend_headers = make_user()
    stranger, stranger_headers = make_user()
    _, moderator = make_user(UserRole.moderator)
    post = make_post()
    draft = make_post()
    assert cclient.get(f"{BASE}/following/activity").status_code == 401
    assert (
        cclient.get(f"{BASE}/following/activity", headers=my_headers).json()["count"]
        == 0
    )
    follow(cclient, my_headers, friend.username)
    old = add_comment(cclient, friend_headers, post.id, body="Friend one")
    add_comment(cclient, stranger_headers, post.id, body="Not followed")
    add_comment(cclient, my_headers, post.id, body="My own")
    hidden = add_comment(cclient, friend_headers, post.id, body="Friend hidden")
    on_draft = add_comment(cclient, friend_headers, draft.id, body="Friend draft")
    new = add_comment(cclient, friend_headers, post.id, body="Friend two")
    cclient.post(f"{MOD}/comments/{hidden['id']}/hide", headers=moderator)
    content_service.set_status(session=db, item=draft, status="draft")
    response = cclient.get(f"{BASE}/following/activity", headers=my_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert [c["id"] for c in data["data"]] == [new["id"], old["id"]]
    assert on_draft["id"] not in str(data)
    assert data["data"][0]["author"]["username"] == friend.username
    assert data["data"][0]["target"]["slug"] == post.slug
    assert friend.email not in response.text
    assert stranger.username not in response.text
    # unfollow empties the feed
    cclient.delete(f"{BASE}/users/{friend.username}/follow", headers=my_headers)
    assert (
        cclient.get(f"{BASE}/following/activity", headers=my_headers).json()["count"]
        == 0
    )


def test_deleting_a_user_removes_their_follows(
    cclient: TestClient, db: Session, make_user: MakeUser
) -> None:
    a, a_headers = make_user()
    b, _ = make_user()
    follow(cclient, a_headers, b.username)
    row = db.get(User, a.id)
    assert row is not None
    db.delete(row)
    db.commit()
    assert profile(cclient, b.username)["follower_count"] == 0


def test_random_uuid_is_not_a_username(cclient: TestClient) -> None:
    assert cclient.get(f"{BASE}/users/{uuid.uuid4()}").status_code == 404

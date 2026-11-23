"""Public profiles, follows and the activity feed of the people I follow.

Privacy: nothing here returns an email address. Inactive users do not exist as far as
profiles are concerned (404). `is_suspended` is shown to moderators and above only.
"""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import ColumnElement, and_, delete, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session, col, func, select

from app.core import files
from app.core.roles import UserRole, has_role
from app.core.storage import Storage
from app.models import User
from app.modules.community import events, service
from app.modules.community.events import CommunityEvent, CommunityEventType
from app.modules.community.models import Comment, UserFollow
from app.modules.community.schemas import (
    AuthorPublic,
    AuthorsPublic,
    CommentTargetPublic,
    FollowState,
    ProfilePublic,
    UserCommentPublic,
    UserCommentsPublic,
)
from app.modules.content.models import ContentStatus, Page, Post


def get_active_user(session: Session, username: str) -> User:
    """The active user with this username (case-insensitive), else 404."""
    user = session.exec(select(User).where(User.username == username.lower())).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _count(session: Session, column: Any, value: uuid.UUID) -> int:
    return session.exec(
        select(func.count()).select_from(UserFollow).where(column == value)
    ).one()


def _is_following(session: Session, follower: User | None, followee: User) -> bool:
    if follower is None:
        return False
    return session.get(UserFollow, (follower.id, followee.id)) is not None


# --- comments shown on profiles and in the activity feed ---


def _public_comment_filters(author_filter: ColumnElement[bool]) -> list[Any]:
    """Visible comments of active users on published posts/pages."""
    return [
        author_filter,
        service.visible_clause(),
        col(User.is_active).is_(True),
        or_(
            col(Post.status) == ContentStatus.published,
            col(Page.status) == ContentStatus.published,
        ),
    ]


def _comments_page(
    *,
    session: Session,
    storage: Storage,
    author_filter: ColumnElement[bool],
    skip: int,
    limit: int,
) -> UserCommentsPublic:
    where = _public_comment_filters(author_filter)

    def joined(statement: Any) -> Any:
        return (
            statement.join(User, col(User.id) == col(Comment.author_id))
            .outerjoin(Post, col(Post.id) == col(Comment.post_id))
            .outerjoin(Page, col(Page.id) == col(Comment.page_id))
            .where(and_(*where))
        )

    count = session.exec(joined(select(func.count()).select_from(Comment))).one()
    rows = session.exec(
        joined(select(Comment, Post, Page))
        .order_by(col(Comment.created_at).desc(), col(Comment.id))
        .offset(skip)
        .limit(limit)
    ).all()
    authors = service.authors_public(
        session, storage, {c.author_id for c, _, _ in rows if c.author_id is not None}
    )
    data: list[UserCommentPublic] = []
    for comment, post, page in rows:
        assert comment.author_id is not None  # joined on the author
        target = (
            CommentTargetPublic(
                type="post", id=post.id, title=post.title, slug=post.slug
            )
            if post is not None
            else CommentTargetPublic(
                type="page", id=page.id, title=page.title, slug=page.slug
            )
        )
        data.append(
            UserCommentPublic(
                id=comment.id,
                author=authors[comment.author_id],
                body=comment.body,
                parent_id=comment.parent_id,
                created_at=comment.created_at,
                like_count=comment.like_count,
                target=target,
            )
        )
    return UserCommentsPublic(data=data, count=count)


def _comment_count(session: Session, author_id: uuid.UUID) -> int:
    statement = (
        select(func.count())
        .select_from(Comment)
        .join(User, col(User.id) == col(Comment.author_id))
        .outerjoin(Post, col(Post.id) == col(Comment.post_id))
        .outerjoin(Page, col(Page.id) == col(Comment.page_id))
        .where(and_(*_public_comment_filters(col(Comment.author_id) == author_id)))
    )
    return session.exec(statement).one()


# --- profiles ---


def read_profile(
    *, session: Session, storage: Storage, username: str, viewer: User | None
) -> ProfilePublic:
    user = get_active_user(session, username)
    avatar_url = files.to_user_public(
        session=session, storage=storage, user=user
    ).avatar_url
    profile = ProfilePublic(
        id=user.id,
        username=user.username,
        display_name=service.display_name(user),
        avatar_url=avatar_url,
        bio=user.bio,
        joined_at=user.created_at,
        comment_count=_comment_count(session, user.id),
        follower_count=_count(session, col(UserFollow.followee_id), user.id),
        following_count=_count(session, col(UserFollow.follower_id), user.id),
    )
    if viewer is not None:
        profile.followed_by_me = _is_following(session, viewer, user)
        if has_role(viewer, UserRole.moderator):
            profile.is_suspended = (
                service.active_suspension(session, user.id) is not None
            )
    return profile


def read_user_comments(
    *, session: Session, storage: Storage, username: str, skip: int, limit: int
) -> UserCommentsPublic:
    user = get_active_user(session, username)
    return _comments_page(
        session=session,
        storage=storage,
        author_filter=col(Comment.author_id) == user.id,
        skip=skip,
        limit=limit,
    )


# --- follows ---


def follow(*, session: Session, user: User, username: str) -> FollowState:
    """Follow a member. Idempotent. Suspended members may follow."""
    target = get_active_user(session, username)
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="You can't follow yourself")
    inserted = (
        session.exec(
            pg_insert(UserFollow)
            .values(
                follower_id=user.id, followee_id=target.id, created_at=service.now()
            )
            .on_conflict_do_nothing()
            .returning(col(UserFollow.follower_id))
        ).first()
        is not None
    )
    session.commit()
    if inserted:
        events.emit(
            CommunityEvent(
                type=CommunityEventType.user_followed,
                actor_id=user.id,
                recipient_id=target.id,
            )
        )
    return _state(session, user, target)


def unfollow(*, session: Session, user: User, username: str) -> FollowState:
    """Stop following. Idempotent."""
    target = get_active_user(session, username)
    session.connection().execute(
        delete(UserFollow).where(
            col(UserFollow.follower_id) == user.id,
            col(UserFollow.followee_id) == target.id,
        )
    )
    session.commit()
    return _state(session, user, target)


def _state(session: Session, user: User, target: User) -> FollowState:
    return FollowState(
        following=_is_following(session, user, target),
        follower_count=_count(session, col(UserFollow.followee_id), target.id),
    )


def _list_authors(
    *,
    session: Session,
    storage: Storage,
    user_column: Any,
    where_column: Any,
    owner_id: uuid.UUID,
    skip: int,
    limit: int,
) -> AuthorsPublic:
    """Active users linked through `user_follow`, newest follow first."""
    base = (
        select(UserFollow.created_at, User)
        .join(User, col(User.id) == user_column)
        .where(where_column == owner_id, col(User.is_active).is_(True))
    )
    count = session.exec(
        select(func.count())
        .select_from(UserFollow)
        .join(User, col(User.id) == user_column)
        .where(where_column == owner_id, col(User.is_active).is_(True))
    ).one()
    rows = session.exec(
        base.order_by(col(UserFollow.created_at).desc(), col(User.id))
        .offset(skip)
        .limit(limit)
    ).all()
    authors = service.authors_public(session, storage, {u.id for _, u in rows})
    ordered: list[AuthorPublic] = [authors[u.id] for _, u in rows]
    return AuthorsPublic(data=ordered, count=count)


def list_followers(
    *, session: Session, storage: Storage, username: str, skip: int, limit: int
) -> AuthorsPublic:
    user = get_active_user(session, username)
    return _list_authors(
        session=session,
        storage=storage,
        user_column=col(UserFollow.follower_id),
        where_column=col(UserFollow.followee_id),
        owner_id=user.id,
        skip=skip,
        limit=limit,
    )


def list_following(
    *, session: Session, storage: Storage, username: str, skip: int, limit: int
) -> AuthorsPublic:
    user = get_active_user(session, username)
    return _list_authors(
        session=session,
        storage=storage,
        user_column=col(UserFollow.followee_id),
        where_column=col(UserFollow.follower_id),
        owner_id=user.id,
        skip=skip,
        limit=limit,
    )


def following_activity(
    *, session: Session, storage: Storage, user: User, skip: int, limit: int
) -> UserCommentsPublic:
    """Recent visible comments of the people I follow, newest first."""
    followed = select(UserFollow.followee_id).where(UserFollow.follower_id == user.id)
    return _comments_page(
        session=session,
        storage=storage,
        author_filter=col(Comment.author_id).in_(followed),
        skip=skip,
        limit=limit,
    )

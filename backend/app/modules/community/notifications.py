"""In-app notifications: created from community events, listed and marked as read.

Rules: nobody is notified about their own actions; a like by the same person on the same
comment (and a repeated follow) creates no second notification while the first one is
still unread. An unlike or unfollow does not delete a notification.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, update
from sqlmodel import Session, col, func, select

from app.core.storage import Storage
from app.models import User
from app.modules.community import service
from app.modules.community.events import CommunityEvent, CommunityEventType
from app.modules.community.models import Comment, Notification, NotificationType
from app.modules.community.schemas import (
    CommentTargetPublic,
    NotificationPublic,
    NotificationsPublic,
    UnreadCount,
)
from app.modules.content.models import ContentStatus, Page, Post

SNIPPET_LENGTH = 140
RETENTION = timedelta(days=90)

_TYPES: dict[CommunityEventType, NotificationType] = {
    CommunityEventType.comment_replied: NotificationType.comment_replied,
    CommunityEventType.comment_liked: NotificationType.comment_liked,
    CommunityEventType.comment_hidden: NotificationType.comment_moderated,
    CommunityEventType.comment_deleted_by_moderator: NotificationType.comment_moderated,
    CommunityEventType.user_followed: NotificationType.new_follower,
}


def _has_unread_duplicate(
    session: Session,
    *,
    recipient_id: uuid.UUID,
    type_: NotificationType,
    actor_id: uuid.UUID,
    comment_id: uuid.UUID | None,
) -> bool:
    statement = select(Notification.id).where(
        Notification.recipient_id == recipient_id,
        Notification.type == type_,
        Notification.actor_id == actor_id,
        col(Notification.read_at).is_(None),
    )
    if comment_id is not None:
        statement = statement.where(Notification.comment_id == comment_id)
    return session.exec(statement).first() is not None


def handle_event(session: Session, event: CommunityEvent) -> Notification | None:
    """Create the notification for an event; None when nothing should be created."""
    if event.recipient_id is None or event.recipient_id == event.actor_id:
        return None
    if session.get(User, event.recipient_id) is None:
        return None
    type_ = _TYPES[event.type]
    # The comment may be really deleted by now (moderator delete without replies).
    comment_id = event.comment_id
    if comment_id is not None and session.get(Comment, comment_id) is None:
        comment_id = None
    if type_ in (
        NotificationType.comment_liked,
        NotificationType.new_follower,
    ) and _has_unread_duplicate(
        session,
        recipient_id=event.recipient_id,
        type_=type_,
        actor_id=event.actor_id,
        comment_id=comment_id,
    ):
        return None
    notification = Notification(
        recipient_id=event.recipient_id,
        type=type_,
        actor_id=event.actor_id,
        comment_id=comment_id,
        post_id=event.target_id if event.target_type == "post" else None,
        page_id=event.target_id if event.target_type == "page" else None,
        created_at=service.now(),
    )
    session.add(notification)
    session.commit()
    return notification


def _snippet(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= SNIPPET_LENGTH:
        return flat
    return flat[: SNIPPET_LENGTH - 1].rstrip() + "…"


def _to_public(
    session: Session, storage: Storage, rows: Sequence[Notification]
) -> list[NotificationPublic]:
    actors = service.authors_public(
        session, storage, {r.actor_id for r in rows if r.actor_id is not None}
    )
    comment_ids = {r.comment_id for r in rows if r.comment_id is not None}
    comments = {
        c.id: c
        for c in session.exec(
            select(Comment).where(col(Comment.id).in_(comment_ids))
        ).all()
    }
    post_ids = {r.post_id for r in rows if r.post_id is not None}
    page_ids = {r.page_id for r in rows if r.page_id is not None}
    posts = {
        p.id: p
        for p in session.exec(select(Post).where(col(Post.id).in_(post_ids))).all()
    }
    pages = {
        p.id: p
        for p in session.exec(select(Page).where(col(Page.id).in_(page_ids))).all()
    }
    result: list[NotificationPublic] = []
    for row in rows:
        comment = comments.get(row.comment_id) if row.comment_id else None
        snippet: str | None = None
        # Never leak a comment that is not public, except to its own author.
        if (
            comment is not None
            and comment.deleted_at is None
            and (service.is_visible(comment) or comment.author_id == row.recipient_id)
        ):
            snippet = _snippet(comment.body)
        target: CommentTargetPublic | None = None
        post = posts.get(row.post_id) if row.post_id else None
        if post is not None and post.status == ContentStatus.published:
            target = CommentTargetPublic(
                type="post", id=post.id, title=post.title, slug=post.slug
            )
        page = pages.get(row.page_id) if row.page_id else None
        if page is not None and page.status == ContentStatus.published:
            target = CommentTargetPublic(
                type="page", id=page.id, title=page.title, slug=page.slug
            )
        result.append(
            NotificationPublic(
                id=row.id,
                type=row.type,
                actor=actors.get(row.actor_id) if row.actor_id else None,
                comment_id=comment.id if comment is not None else None,
                comment_snippet=snippet,
                target=target,
                created_at=row.created_at,
                read=row.read_at is not None,
            )
        )
    return result


def list_notifications(
    *, session: Session, storage: Storage, user: User, skip: int, limit: int
) -> NotificationsPublic:
    where = Notification.recipient_id == user.id
    count = session.exec(
        select(func.count()).select_from(Notification).where(where)
    ).one()
    rows = session.exec(
        select(Notification)
        .where(where)
        .order_by(col(Notification.created_at).desc(), col(Notification.id))
        .offset(skip)
        .limit(limit)
    ).all()
    return NotificationsPublic(data=_to_public(session, storage, rows), count=count)


def unread_count(*, session: Session, user: User) -> UnreadCount:
    count = session.exec(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.recipient_id == user.id,
            col(Notification.read_at).is_(None),
        )
    ).one()
    return UnreadCount(unread_count=count)


def mark_read(
    *, session: Session, user: User, notification_id: uuid.UUID
) -> UnreadCount:
    """Mark one of my notifications as read (idempotent); someone else's is a 404."""
    row = session.get(Notification, notification_id)
    if row is None or row.recipient_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    if row.read_at is None:
        row.read_at = service.now()
        session.add(row)
        session.commit()
    return unread_count(session=session, user=user)


def mark_all_read(*, session: Session, user: User) -> UnreadCount:
    session.connection().execute(
        update(Notification)
        .where(
            col(Notification.recipient_id) == user.id,
            col(Notification.read_at).is_(None),
        )
        .values(read_at=service.now())
    )
    session.commit()
    return UnreadCount(unread_count=0)


def cleanup_old_notifications(
    *, session: Session, now: datetime | None = None, retention: timedelta = RETENTION
) -> int:
    """Delete notifications older than the retention period (90 days); returns how many."""
    cutoff = (now or service.now()) - retention
    result = session.connection().execute(
        delete(Notification).where(col(Notification.created_at) < cutoff)
    )
    session.commit()
    return int(result.rowcount)

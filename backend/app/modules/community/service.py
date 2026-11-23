"""Community business logic: comments, likes, reports, suspensions, moderation.

Routes stay thin and call these functions. Errors are raised as `HTTPException`.

Visibility rules (see docs/ARCHITECTURE.md, "Community module"):
- A comment is *visible* when its status is `visible` and it is not soft-deleted.
- Public lists show visible comments. A top-level comment that is not visible stays in
  the list as a placeholder only while it has at least one visible reply.
- Comments follow their post/page: they are not listed while it is a draft (the list
  answers 404) and they are deleted with it (foreign keys ON DELETE CASCADE).
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import ColumnElement, and_, delete, exists, or_, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from sqlmodel import Session, col, func, select

from app.core import files
from app.core.config import settings
from app.core.roles import UserRole
from app.core.storage import Storage
from app.models import Message, User
from app.modules.community import events
from app.modules.community.events import CommunityEvent, CommunityEventType
from app.modules.community.models import (
    Comment,
    CommentLike,
    CommentReport,
    CommentStatus,
    CommunitySuspension,
    PostLike,
    PostLikeCount,
    ReportStatus,
)
from app.modules.community.schemas import (
    AuthorPublic,
    CommentCreate,
    CommentPublic,
    CommentSort,
    CommentsPublic,
    CommentState,
    CommentTargetPublic,
    CommentUpdate,
    LikeState,
    ModerationComment,
    ModerationQueue,
    MySuspension,
    QueueFilter,
    ReplyPublic,
    ReportCreate,
    ReportPublic,
    SuspensionCreate,
    SuspensionPublic,
    SuspensionsPublic,
    TargetType,
)
from app.modules.content import service as content_service
from app.modules.content.models import ContentStatus, Page, Post

EDIT_WINDOW = timedelta(minutes=15)
COMMENT_RATE_WINDOW = timedelta(hours=1)
REPORT_RATE_WINDOW = timedelta(hours=24)

DELETED_PLACEHOLDER = "[deleted]"
REMOVED_PLACEHOLDER = "[removed by a moderator]"
SUSPENDED_DETAIL = "You are suspended from commenting"


def now() -> datetime:
    """The clock of this module. Tests replace it to move time without sleeping."""
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    """Naive datetimes come back from the database; they are stored as UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _lock(session: Session, key: str) -> None:
    """Serialise one user's creates (released at commit), so parallel requests can't
    overshoot a rate limit."""
    session.connection().execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key}
    )


# --- small helpers ---


def display_name(user: User) -> str:
    return user.full_name or f"Member {str(user.id)[:8]}"


def _is_protected(user: User) -> bool:
    return user.is_superuser or user.role == UserRole.admin


def _state(comment: Comment) -> CommentState:
    if comment.deleted_at is not None:
        return (
            CommentState.removed
            if comment.removed_by_moderator
            else CommentState.deleted
        )
    if comment.status == CommentStatus.hidden:
        return CommentState.hidden
    return CommentState.visible


def _target(comment: Comment) -> tuple[TargetType, uuid.UUID]:
    if comment.post_id is not None:
        return "post", comment.post_id
    assert comment.page_id is not None  # the table has a check constraint
    return "page", comment.page_id


def is_visible(comment: Comment) -> bool:
    return _state(comment) == CommentState.visible


def visible_clause() -> ColumnElement[bool]:
    return and_(
        col(Comment.status) == CommentStatus.visible,
        col(Comment.deleted_at).is_(None),
    )


def authors_public(
    session: Session, storage: Storage, user_ids: set[uuid.UUID]
) -> dict[uuid.UUID, AuthorPublic]:
    """Display name + avatar URL for many users, in two queries (no N+1)."""
    if not user_ids:
        return {}
    users = session.exec(select(User).where(col(User.id).in_(user_ids))).all()
    publics = files.to_users_public(session=session, storage=storage, users=users)
    return {
        user.id: AuthorPublic(
            id=user.id,
            username=user.username,
            display_name=display_name(user),
            avatar_url=public.avatar_url,
        )
        for user, public in zip(users, publics, strict=True)
    }


# --- targets and lookups ---


def get_published_target(
    session: Session, target_type: TargetType, target_id: uuid.UUID
) -> Post | Page:
    """The post/page, or 404 when it does not exist or is not published."""
    item = (
        content_service.get_post(session, target_id)
        if target_type == "post"
        else content_service.get_page(session, target_id)
    )
    if item.status != ContentStatus.published:
        raise HTTPException(status_code=404, detail=f"{target_type.title()} not found")
    return item


def _get_comment(session: Session, comment_id: uuid.UUID) -> Comment:
    comment = session.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    return comment


def _get_visible_comment(session: Session, comment_id: uuid.UUID) -> Comment:
    """A visible comment on a published post/page, else 404 (like a missing one)."""
    comment = _get_comment(session, comment_id)
    if _state(comment) != CommentState.visible:
        raise HTTPException(status_code=404, detail="Comment not found")
    get_published_target(session, *_target(comment))
    return comment


def _event(
    type_: CommunityEventType,
    comment: Comment,
    actor: User,
    recipient_id: uuid.UUID | None,
) -> CommunityEvent:
    target_type, target_id = _target(comment)
    return CommunityEvent(
        type=type_,
        comment_id=comment.id,
        actor_id=actor.id,
        recipient_id=recipient_id,
        target_type=target_type,
        target_id=target_id,
    )


def _emit(
    type_: CommunityEventType,
    comment: Comment,
    actor: User,
    recipient_id: uuid.UUID | None,
) -> None:
    events.emit(_event(type_, comment, actor, recipient_id))


# --- suspensions ---


def active_suspension(
    session: Session, user_id: uuid.UUID
) -> CommunitySuspension | None:
    current = now()
    return session.exec(
        select(CommunitySuspension)
        .where(
            CommunitySuspension.user_id == user_id,
            col(CommunitySuspension.ended_at).is_(None),
            or_(
                col(CommunitySuspension.until).is_(None),
                col(CommunitySuspension.until) > current,
            ),
        )
        .order_by(col(CommunitySuspension.created_at).desc())
    ).first()


def ensure_not_suspended(session: Session, user: User) -> None:
    if active_suspension(session, user.id) is not None:
        raise HTTPException(status_code=403, detail=SUSPENDED_DETAIL)


def my_suspension(session: Session, user: User) -> MySuspension:
    suspension = active_suspension(session, user.id)
    if suspension is None:
        return MySuspension(suspended=False)
    return MySuspension(
        suspended=True, until=suspension.until, reason=suspension.reason
    )


def _ensure_can_moderate(actor: User, target: User | None) -> None:
    """Same rule as user management (task 005): only superusers act on admins and
    superusers. `target` is None when the author no longer exists."""
    if actor.is_superuser or target is None or target.id == actor.id:
        return
    if _is_protected(target):
        raise HTTPException(
            status_code=403,
            detail="Only superusers can moderate admins and superusers",
        )


def _ensure_can_moderate_comment(
    session: Session, actor: User, comment: Comment
) -> None:
    author = session.get(User, comment.author_id) if comment.author_id else None
    _ensure_can_moderate(actor, author)


def _to_suspensions(
    session: Session, storage: Storage, rows: Sequence[CommunitySuspension]
) -> list[SuspensionPublic]:
    ids: set[uuid.UUID] = {r.user_id for r in rows}
    ids |= {r.created_by for r in rows if r.created_by is not None}
    authors = authors_public(session, storage, ids)
    current = now()
    return [
        SuspensionPublic(
            id=r.id,
            user=authors.get(r.user_id),
            user_id=r.user_id,
            until=r.until,
            reason=r.reason,
            created_by=authors.get(r.created_by) if r.created_by else None,
            created_at=r.created_at,
            ended_at=r.ended_at,
            active=r.ended_at is None and (r.until is None or _utc(r.until) > current),
        )
        for r in rows
    ]


def create_suspension(
    *, session: Session, storage: Storage, actor: User, data: SuspensionCreate
) -> SuspensionPublic:
    target = session.get(User, data.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == actor.id:
        raise HTTPException(status_code=400, detail="You can't suspend yourself")
    _ensure_can_moderate(actor, target)
    if data.until is not None and _utc(data.until) <= now():
        raise HTTPException(status_code=400, detail="`until` must be in the future")
    if active_suspension(session, target.id) is not None:
        raise HTTPException(
            status_code=409,
            detail="The user is already suspended; end that suspension first",
        )
    row = CommunitySuspension(
        user_id=target.id,
        until=data.until,
        reason=data.reason.strip() or None if data.reason else None,
        created_by=actor.id,
        created_at=now(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_suspensions(session, storage, [row])[0]


def end_suspension(
    *, session: Session, storage: Storage, actor: User, suspension_id: uuid.UUID
) -> SuspensionPublic:
    row = session.get(CommunitySuspension, suspension_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Suspension not found")
    _ensure_can_moderate(actor, session.get(User, row.user_id))
    if row.ended_at is None:
        row.ended_at = now()
        session.add(row)
        session.commit()
        session.refresh(row)
    return _to_suspensions(session, storage, [row])[0]


def list_suspensions(
    *,
    session: Session,
    storage: Storage,
    active_only: bool,
    skip: int,
    limit: int,
) -> SuspensionsPublic:
    statement = select(CommunitySuspension)
    if active_only:
        statement = statement.where(
            col(CommunitySuspension.ended_at).is_(None),
            or_(
                col(CommunitySuspension.until).is_(None),
                col(CommunitySuspension.until) > now(),
            ),
        )
    count = session.exec(select(func.count()).select_from(statement.subquery())).one()
    rows = session.exec(
        statement.order_by(col(CommunitySuspension.created_at).desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return SuspensionsPublic(data=_to_suspensions(session, storage, rows), count=count)


# --- building responses ---


def _liked_ids(
    session: Session, viewer: User | None, comment_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    if viewer is None or not comment_ids:
        return set()
    return set(
        session.exec(
            select(CommentLike.comment_id).where(
                CommentLike.user_id == viewer.id,
                col(CommentLike.comment_id).in_(comment_ids),
            )
        )
    )


def _to_replies(
    session: Session,
    storage: Storage,
    comments: Sequence[Comment],
    viewer: User | None,
) -> list[ReplyPublic]:
    """Public view: placeholders hide the body and the author."""
    authors = authors_public(
        session, storage, {c.author_id for c in comments if c.author_id is not None}
    )
    liked = _liked_ids(session, viewer, [c.id for c in comments])
    current = now()
    result: list[ReplyPublic] = []
    for c in comments:
        state = _state(c)
        shown = state == CommentState.visible
        placeholder = (
            DELETED_PLACEHOLDER
            if state == CommentState.deleted
            else REMOVED_PLACEHOLDER
        )
        target_type, target_id = _target(c)
        result.append(
            ReplyPublic(
                id=c.id,
                target_type=target_type,
                target_id=target_id,
                parent_id=c.parent_id,
                author=authors.get(c.author_id) if shown and c.author_id else None,
                body=c.body if shown else placeholder,
                state=state,
                created_at=c.created_at,
                edited_at=c.edited_at,
                like_count=c.like_count if shown else 0,
                liked_by_me=shown and c.id in liked,
                can_edit=(
                    shown
                    and viewer is not None
                    and c.author_id == viewer.id
                    and current - _utc(c.created_at) <= EDIT_WINDOW
                ),
            )
        )
    return result


def _nest(top: ReplyPublic, replies: list[ReplyPublic]) -> CommentPublic:
    return CommentPublic(**top.model_dump(), replies=replies)


def post_like_state(
    session: Session, post_id: uuid.UUID, viewer: User | None
) -> LikeState:
    stat = session.get(PostLikeCount, post_id)
    liked = (
        viewer is not None and session.get(PostLike, (post_id, viewer.id)) is not None
    )
    return LikeState(like_count=stat.like_count if stat else 0, liked_by_me=liked)


# --- listing ---


def list_comments(
    *,
    session: Session,
    storage: Storage,
    target_type: TargetType,
    target_id: uuid.UUID,
    viewer: User | None,
    sort: CommentSort,
    skip: int,
    limit: int,
) -> CommentsPublic:
    get_published_target(session, target_type, target_id)
    reply = aliased(Comment)
    has_visible_reply = exists().where(
        col(reply.parent_id) == col(Comment.id),
        col(reply.status) == CommentStatus.visible,
        col(reply.deleted_at).is_(None),
    )
    target_col = col(Comment.post_id if target_type == "post" else Comment.page_id)
    where = [
        target_col == target_id,
        col(Comment.parent_id).is_(None),
        or_(visible_clause(), has_visible_reply),
    ]
    count = session.exec(select(func.count()).select_from(Comment).where(*where)).one()
    order = (
        col(Comment.created_at).desc()
        if sort == CommentSort.newest
        else col(Comment.created_at).asc()
    )
    tops = session.exec(
        select(Comment)
        .where(*where)
        .order_by(order, col(Comment.id))
        .offset(skip)
        .limit(limit)
    ).all()
    replies = (
        session.exec(
            select(Comment)
            .where(col(Comment.parent_id).in_([t.id for t in tops]), visible_clause())
            .order_by(col(Comment.created_at).asc(), col(Comment.id))
        ).all()
        if tops
        else []
    )
    # One batch for the avatars/likes of everything on the page.
    public = {r.id: r for r in _to_replies(session, storage, [*tops, *replies], viewer)}
    by_parent: dict[uuid.UUID, list[ReplyPublic]] = {}
    for r in replies:
        if r.parent_id is not None:
            by_parent.setdefault(r.parent_id, []).append(public[r.id])
    result = CommentsPublic(
        data=[_nest(public[t.id], by_parent.get(t.id, [])) for t in tops],
        count=count,
    )
    if target_type == "post":
        likes = post_like_state(session, target_id, viewer)
        result.post_like_count = likes.like_count
        result.post_liked_by_me = likes.liked_by_me
    return result


def _one_public(
    session: Session, storage: Storage, comment: Comment, viewer: User | None
) -> CommentPublic:
    return _nest(_to_replies(session, storage, [comment], viewer)[0], [])


# --- creating, editing, deleting (authors) ---


def create_comment(
    *,
    session: Session,
    storage: Storage,
    user: User,
    target_type: TargetType,
    target_id: uuid.UUID,
    data: CommentCreate,
) -> CommentPublic:
    ensure_not_suspended(session, user)
    get_published_target(session, target_type, target_id)
    parent: Comment | None = None
    if data.parent_id is not None:
        parent = session.get(Comment, data.parent_id)
        if parent is None or _target(parent) != (target_type, target_id):
            raise HTTPException(status_code=404, detail="Parent comment not found")
        if parent.parent_id is not None:
            raise HTTPException(
                status_code=400,
                detail="You can't reply to a reply; reply to the top-level comment",
            )
        if _state(parent) != CommentState.visible:
            raise HTTPException(
                status_code=400, detail="You can't reply to a removed comment"
            )

    _lock(session, f"community-comment:{user.id}")
    if not user.is_superuser:
        recent = session.exec(
            select(func.count())
            .select_from(Comment)
            .where(
                Comment.author_id == user.id,
                col(Comment.created_at) >= now() - COMMENT_RATE_WINDOW,
            )
        ).one()
        if recent >= settings.COMMENTS_PER_USER_PER_HOUR:
            raise HTTPException(
                status_code=429, detail="Too many comments, try again later"
            )
    comment = Comment(
        post_id=target_id if target_type == "post" else None,
        page_id=target_id if target_type == "page" else None,
        author_id=user.id,
        parent_id=parent.id if parent else None,
        body=data.body,
        created_at=now(),
    )
    session.add(comment)
    session.commit()  # also releases the advisory lock
    session.refresh(comment)
    if parent is not None and parent.author_id != user.id:
        _emit(CommunityEventType.comment_replied, comment, user, parent.author_id)
    return _one_public(session, storage, comment, user)


def update_comment(
    *,
    session: Session,
    storage: Storage,
    user: User,
    comment_id: uuid.UUID,
    data: CommentUpdate,
) -> CommentPublic:
    ensure_not_suspended(session, user)
    comment = _get_visible_comment(session, comment_id)
    if comment.author_id != user.id:
        raise HTTPException(
            status_code=403, detail="You can only edit your own comments"
        )
    if now() - _utc(comment.created_at) > EDIT_WINDOW:
        raise HTTPException(
            status_code=403,
            detail="Comments can only be edited within 15 minutes",
        )
    comment.body = data.body
    comment.edited_at = now()
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return _one_public(session, storage, comment, user)


def _delete_comment(*, session: Session, comment: Comment, by_moderator: bool) -> None:
    """Soft delete (placeholder) when the comment has replies, else a real delete."""
    has_replies = (
        session.exec(
            select(func.count())
            .select_from(Comment)
            .where(Comment.parent_id == comment.id)
        ).one()
        > 0
    )
    if has_replies:
        comment.body = REMOVED_PLACEHOLDER if by_moderator else DELETED_PLACEHOLDER
        comment.deleted_at = now()
        comment.removed_by_moderator = by_moderator
        session.add(comment)
        # Nothing left to moderate: close its open reports.
        session.connection().execute(
            update(CommentReport)
            .where(
                col(CommentReport.comment_id) == comment.id,
                col(CommentReport.status) == ReportStatus.open,
            )
            .values(status=ReportStatus.resolved, resolved_at=now())
        )
    else:
        session.delete(comment)  # replies, likes and reports go with it (CASCADE)
    session.commit()


def delete_own_comment(
    *, session: Session, user: User, comment_id: uuid.UUID
) -> Message:
    """Allowed while suspended: removing your own words is never harmful."""
    comment = _get_comment(session, comment_id)
    if comment.author_id != user.id:
        raise HTTPException(
            status_code=403, detail="You can only delete your own comments"
        )
    if comment.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Comment not found")
    _delete_comment(session=session, comment=comment, by_moderator=False)
    return Message(message="Comment deleted")


# --- likes ---


def _comment_like_state(session: Session, comment: Comment, viewer: User) -> LikeState:
    session.refresh(comment)
    return LikeState(
        like_count=comment.like_count,
        liked_by_me=session.get(CommentLike, (comment.id, viewer.id)) is not None,
    )


def like_comment(*, session: Session, user: User, comment_id: uuid.UUID) -> LikeState:
    ensure_not_suspended(session, user)
    comment = _get_visible_comment(session, comment_id)
    inserted = (
        session.exec(
            pg_insert(CommentLike)
            .values(comment_id=comment.id, user_id=user.id, created_at=now())
            .on_conflict_do_nothing()
            .returning(col(CommentLike.user_id))
        ).first()
        is not None
    )
    if inserted:
        session.exec(
            update(Comment)
            .where(col(Comment.id) == comment.id)
            .values(like_count=Comment.like_count + 1)
        )
    session.commit()
    if inserted and comment.author_id != user.id:
        _emit(CommunityEventType.comment_liked, comment, user, comment.author_id)
    return _comment_like_state(session, comment, user)


def unlike_comment(*, session: Session, user: User, comment_id: uuid.UUID) -> LikeState:
    comment = _get_comment(session, comment_id)
    removed = (
        session.exec(
            delete(CommentLike)
            .where(
                col(CommentLike.comment_id) == comment.id,
                col(CommentLike.user_id) == user.id,
            )
            .returning(col(CommentLike.user_id))
        ).first()
        is not None
    )
    if removed:
        session.exec(
            update(Comment)
            .where(col(Comment.id) == comment.id)
            .values(like_count=func.greatest(Comment.like_count - 1, 0))
        )
    session.commit()
    return _comment_like_state(session, comment, user)


def like_post(*, session: Session, user: User, post_id: uuid.UUID) -> LikeState:
    ensure_not_suspended(session, user)
    get_published_target(session, "post", post_id)
    inserted = (
        session.exec(
            pg_insert(PostLike)
            .values(post_id=post_id, user_id=user.id, created_at=now())
            .on_conflict_do_nothing()
            .returning(col(PostLike.user_id))
        ).first()
        is not None
    )
    if inserted:
        counter = pg_insert(PostLikeCount).values(post_id=post_id, like_count=1)
        session.exec(
            counter.on_conflict_do_update(
                index_elements=[col(PostLikeCount.post_id)],
                set_={"like_count": PostLikeCount.like_count + 1},
            )
        )
    session.commit()
    return post_like_state(session, post_id, user)


def unlike_post(*, session: Session, user: User, post_id: uuid.UUID) -> LikeState:
    content_service.get_post(session, post_id)  # 404 for unknown posts
    removed = (
        session.exec(
            delete(PostLike)
            .where(col(PostLike.post_id) == post_id, col(PostLike.user_id) == user.id)
            .returning(col(PostLike.user_id))
        ).first()
        is not None
    )
    if removed:
        session.exec(
            update(PostLikeCount)
            .where(col(PostLikeCount.post_id) == post_id)
            .values(like_count=func.greatest(PostLikeCount.like_count - 1, 0))
        )
    session.commit()
    return post_like_state(session, post_id, user)


# --- reports ---


def report_comment(
    *, session: Session, user: User, comment_id: uuid.UUID, data: ReportCreate
) -> Message:
    ensure_not_suspended(session, user)
    comment = _get_visible_comment(session, comment_id)
    if comment.author_id == user.id:
        raise HTTPException(status_code=400, detail="You can't report your own comment")
    _lock(session, f"community-report:{user.id}")
    already = session.exec(
        select(func.count())
        .select_from(CommentReport)
        .where(
            CommentReport.comment_id == comment.id,
            CommentReport.reporter_id == user.id,
        )
    ).one()
    if already:
        raise HTTPException(status_code=409, detail="You already reported this comment")
    if not user.is_superuser:
        recent = session.exec(
            select(func.count())
            .select_from(CommentReport)
            .where(
                CommentReport.reporter_id == user.id,
                col(CommentReport.created_at) >= now() - REPORT_RATE_WINDOW,
            )
        ).one()
        if recent >= settings.REPORTS_PER_USER_PER_DAY:
            raise HTTPException(
                status_code=429, detail="Too many reports, try again later"
            )
    session.add(
        CommentReport(
            comment_id=comment.id,
            reporter_id=user.id,
            reason=data.reason,
            note=data.note,
            created_at=now(),
        )
    )
    try:
        session.commit()
    except IntegrityError:  # a parallel request reported it first
        session.rollback()
        raise HTTPException(status_code=409, detail="You already reported this comment")
    return Message(message="Report received")


# --- moderation ---


def _open_reports(session: Session, comment_ids: list[uuid.UUID]) -> Sequence[Any]:
    return session.exec(
        select(CommentReport)
        .where(
            col(CommentReport.comment_id).in_(comment_ids),
            CommentReport.status == ReportStatus.open,
        )
        .order_by(col(CommentReport.created_at).asc())
    ).all()


def moderation_queue(
    *,
    session: Session,
    storage: Storage,
    queue_filter: QueueFilter | None,
    skip: int,
    limit: int,
) -> ModerationQueue:
    reported = exists().where(
        col(CommentReport.comment_id) == col(Comment.id),
        col(CommentReport.status) == ReportStatus.open,
    )
    hidden = col(Comment.status) == CommentStatus.hidden
    condition = {
        QueueFilter.reported: reported,
        QueueFilter.hidden: hidden,
        None: or_(reported, hidden),
    }[queue_filter]
    where = [col(Comment.deleted_at).is_(None), condition]
    count = session.exec(select(func.count()).select_from(Comment).where(*where)).one()
    comments = session.exec(
        select(Comment)
        .where(*where)
        .order_by(col(Comment.created_at).desc(), col(Comment.id))
        .offset(skip)
        .limit(limit)
    ).all()
    reports = _open_reports(session, [c.id for c in comments]) if comments else []
    ids = {c.author_id for c in comments if c.author_id is not None}
    ids |= {r.reporter_id for r in reports}
    authors = authors_public(session, storage, ids)
    by_comment: dict[uuid.UUID, list[ReportPublic]] = {}
    for r in reports:
        by_comment.setdefault(r.comment_id, []).append(
            ReportPublic(
                id=r.id,
                reason=r.reason,
                note=r.note,
                reporter=authors.get(r.reporter_id),
                created_at=r.created_at,
            )
        )
    post_ids = {c.post_id for c in comments if c.post_id is not None}
    page_ids = {c.page_id for c in comments if c.page_id is not None}
    posts = (
        {p.id: p for p in session.exec(select(Post).where(col(Post.id).in_(post_ids)))}
        if post_ids
        else {}
    )
    pages = (
        {p.id: p for p in session.exec(select(Page).where(col(Page.id).in_(page_ids)))}
        if page_ids
        else {}
    )
    data: list[ModerationComment] = []
    for c in comments:
        target_type, target_id = _target(c)
        content = (
            posts.get(target_id) if target_type == "post" else pages.get(target_id)
        )
        open_reports = by_comment.get(c.id, [])
        data.append(
            ModerationComment(
                id=c.id,
                target_type=target_type,
                target_id=target_id,
                parent_id=c.parent_id,
                author=authors.get(c.author_id) if c.author_id else None,
                body=c.body,
                state=_state(c),
                created_at=c.created_at,
                edited_at=c.edited_at,
                like_count=c.like_count,
                open_report_count=len(open_reports),
                reports=open_reports,
                target=CommentTargetPublic(
                    type=target_type,
                    id=target_id,
                    title=content.title,
                    slug=content.slug,
                )
                if content is not None
                else None,
            )
        )
    return ModerationQueue(data=data, count=count)


def hide_comment(*, session: Session, actor: User, comment_id: uuid.UUID) -> Message:
    comment = _get_comment(session, comment_id)
    _ensure_can_moderate_comment(session, actor, comment)
    if comment.deleted_at is not None:
        raise HTTPException(status_code=400, detail="The comment was deleted")
    if comment.status != CommentStatus.hidden:
        comment.status = CommentStatus.hidden
        session.add(comment)
        session.commit()
        _emit(CommunityEventType.comment_hidden, comment, actor, comment.author_id)
    return Message(message="Comment hidden")


def restore_comment(*, session: Session, actor: User, comment_id: uuid.UUID) -> Message:
    comment = _get_comment(session, comment_id)
    _ensure_can_moderate_comment(session, actor, comment)
    if comment.deleted_at is not None:
        raise HTTPException(
            status_code=400, detail="A deleted comment can't be restored"
        )
    if comment.status != CommentStatus.visible:
        comment.status = CommentStatus.visible
        session.add(comment)
        session.commit()
    return Message(message="Comment restored")


def moderator_delete_comment(
    *, session: Session, actor: User, comment_id: uuid.UUID
) -> Message:
    comment = _get_comment(session, comment_id)
    _ensure_can_moderate_comment(session, actor, comment)
    # Built before the delete: a really deleted row can't be read afterwards.
    event = _event(
        CommunityEventType.comment_deleted_by_moderator,
        comment,
        actor,
        comment.author_id,
    )
    _delete_comment(session=session, comment=comment, by_moderator=True)
    events.emit(event)
    return Message(message="Comment deleted")


def resolve_reports(*, session: Session, actor: User, comment_id: uuid.UUID) -> Message:
    comment = _get_comment(session, comment_id)
    _ensure_can_moderate_comment(session, actor, comment)
    session.connection().execute(
        update(CommentReport)
        .where(
            col(CommentReport.comment_id) == comment.id,
            col(CommentReport.status) == ReportStatus.open,
        )
        .values(status=ReportStatus.resolved, resolved_at=now(), resolved_by=actor.id)
    )
    session.commit()
    return Message(message="Reports resolved")

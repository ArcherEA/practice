"""Community module API, mounted at /api/v1/community.

- Public: list comments of a published post/page, post like state.
- Public: member profiles (`/users/{username}`), their comments, followers, following.
- Logged in: follow / unfollow, activity feed, own notifications.
- Logged in (any role): comment, reply, edit, delete own, like, report.
  Suspended members get 403 on create/edit/like/report.
- `/moderation`: needs `require_role(UserRole.moderator)` (moderator, admin,
  superuser; editors and members get 403).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, SessionDep, StorageDep, require_role
from app.core.roles import UserRole
from app.models import Message, User
from app.modules.community import notifications, profiles, service
from app.modules.community.deps import OptionalUser
from app.modules.community.schemas import (
    AuthorsPublic,
    CommentCreate,
    CommentPublic,
    CommentSort,
    CommentsPublic,
    CommentUpdate,
    FollowState,
    LikeState,
    ModerationQueue,
    MySuspension,
    NotificationsPublic,
    ProfilePublic,
    QueueFilter,
    ReportCreate,
    SuspensionCreate,
    SuspensionPublic,
    SuspensionsPublic,
    UnreadCount,
    UserCommentsPublic,
)

router = APIRouter(prefix="/community", tags=["community"])

ModeratorUser = Annotated[User, Depends(require_role(UserRole.moderator))]
Skip = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]
Sort = Annotated[
    CommentSort, Query(description="Top-level order; replies are oldest first")
]

# --- comments: public reads ---


@router.get("/posts/{post_id}/comments", response_model=CommentsPublic)
def read_post_comments(
    session: SessionDep,
    storage: StorageDep,
    viewer: OptionalUser,
    post_id: uuid.UUID,
    sort: Sort = CommentSort.newest,
    skip: Skip = 0,
    limit: Limit = 20,
) -> CommentsPublic:
    """Comments of a published post (404 otherwise), one level of replies nested."""
    return service.list_comments(
        session=session,
        storage=storage,
        target_type="post",
        target_id=post_id,
        viewer=viewer,
        sort=sort,
        skip=skip,
        limit=limit,
    )


@router.get("/pages/{page_id}/comments", response_model=CommentsPublic)
def read_page_comments(
    session: SessionDep,
    storage: StorageDep,
    viewer: OptionalUser,
    page_id: uuid.UUID,
    sort: Sort = CommentSort.newest,
    skip: Skip = 0,
    limit: Limit = 20,
) -> CommentsPublic:
    """Comments of a published page (404 otherwise), one level of replies nested."""
    return service.list_comments(
        session=session,
        storage=storage,
        target_type="page",
        target_id=page_id,
        viewer=viewer,
        sort=sort,
        skip=skip,
        limit=limit,
    )


@router.get("/posts/{post_id}/like", response_model=LikeState)
def read_post_likes(
    session: SessionDep, viewer: OptionalUser, post_id: uuid.UUID
) -> LikeState:
    service.get_published_target(session, "post", post_id)
    return service.post_like_state(session, post_id, viewer)


# --- comments: members ---


@router.post("/posts/{post_id}/comments", response_model=CommentPublic)
def create_post_comment(
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
    post_id: uuid.UUID,
    comment_in: CommentCreate,
) -> CommentPublic:
    """Comment on a published post, or reply to a top-level comment (`parent_id`)."""
    return service.create_comment(
        session=session,
        storage=storage,
        user=user,
        target_type="post",
        target_id=post_id,
        data=comment_in,
    )


@router.post("/pages/{page_id}/comments", response_model=CommentPublic)
def create_page_comment(
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
    page_id: uuid.UUID,
    comment_in: CommentCreate,
) -> CommentPublic:
    """Comment on a published page, or reply to a top-level comment (`parent_id`)."""
    return service.create_comment(
        session=session,
        storage=storage,
        user=user,
        target_type="page",
        target_id=page_id,
        data=comment_in,
    )


@router.put("/comments/{comment_id}", response_model=CommentPublic)
def update_comment(
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
    comment_id: uuid.UUID,
    comment_in: CommentUpdate,
) -> CommentPublic:
    """Edit your own comment within 15 minutes of posting it."""
    return service.update_comment(
        session=session,
        storage=storage,
        user=user,
        comment_id=comment_id,
        data=comment_in,
    )


@router.delete("/comments/{comment_id}", response_model=Message)
def delete_comment(
    session: SessionDep, user: CurrentUser, comment_id: uuid.UUID
) -> Message:
    """Delete your own comment (a placeholder stays when it has replies)."""
    return service.delete_own_comment(session=session, user=user, comment_id=comment_id)


@router.put("/comments/{comment_id}/like", response_model=LikeState)
def like_comment(
    session: SessionDep, user: CurrentUser, comment_id: uuid.UUID
) -> LikeState:
    """Like a comment. Idempotent: liking twice counts once."""
    return service.like_comment(session=session, user=user, comment_id=comment_id)


@router.delete("/comments/{comment_id}/like", response_model=LikeState)
def unlike_comment(
    session: SessionDep, user: CurrentUser, comment_id: uuid.UUID
) -> LikeState:
    """Remove your like. Idempotent. Allowed while suspended."""
    return service.unlike_comment(session=session, user=user, comment_id=comment_id)


@router.put("/posts/{post_id}/like", response_model=LikeState)
def like_post(session: SessionDep, user: CurrentUser, post_id: uuid.UUID) -> LikeState:
    """Like a published post. Idempotent."""
    return service.like_post(session=session, user=user, post_id=post_id)


@router.delete("/posts/{post_id}/like", response_model=LikeState)
def unlike_post(
    session: SessionDep, user: CurrentUser, post_id: uuid.UUID
) -> LikeState:
    """Remove your like from a post. Idempotent. Allowed while suspended."""
    return service.unlike_post(session=session, user=user, post_id=post_id)


@router.post("/comments/{comment_id}/report", response_model=Message)
def report_comment(
    session: SessionDep,
    user: CurrentUser,
    comment_id: uuid.UUID,
    report_in: ReportCreate,
) -> Message:
    """Report a comment (once per user): spam, abuse or other."""
    return service.report_comment(
        session=session, user=user, comment_id=comment_id, data=report_in
    )


@router.get("/me/suspension", response_model=MySuspension)
def read_my_suspension(session: SessionDep, user: CurrentUser) -> MySuspension:
    """Whether you are currently suspended from commenting, liking and reporting."""
    return service.my_suspension(session, user)


# --- profiles, follows (public reads; logged in to follow) ---


@router.get("/users/{username}", response_model=ProfilePublic)
def read_profile(
    session: SessionDep, storage: StorageDep, viewer: OptionalUser, username: str
) -> ProfilePublic:
    """Public profile by username (case-insensitive). Never contains the email;
    `is_suspended` only for moderators and above. Inactive users give 404."""
    return profiles.read_profile(
        session=session, storage=storage, username=username, viewer=viewer
    )


@router.get("/users/{username}/comments", response_model=UserCommentsPublic)
def read_user_comments(
    session: SessionDep,
    storage: StorageDep,
    username: str,
    skip: Skip = 0,
    limit: Limit = 20,
) -> UserCommentsPublic:
    """A member's recent visible comments, with the post or page they belong to."""
    return profiles.read_user_comments(
        session=session, storage=storage, username=username, skip=skip, limit=limit
    )


@router.get("/users/{username}/followers", response_model=AuthorsPublic)
def read_followers(
    session: SessionDep,
    storage: StorageDep,
    username: str,
    skip: Skip = 0,
    limit: Limit = 20,
) -> AuthorsPublic:
    return profiles.list_followers(
        session=session, storage=storage, username=username, skip=skip, limit=limit
    )


@router.get("/users/{username}/following", response_model=AuthorsPublic)
def read_following(
    session: SessionDep,
    storage: StorageDep,
    username: str,
    skip: Skip = 0,
    limit: Limit = 20,
) -> AuthorsPublic:
    return profiles.list_following(
        session=session, storage=storage, username=username, skip=skip, limit=limit
    )


@router.put("/users/{username}/follow", response_model=FollowState)
def follow_user(session: SessionDep, user: CurrentUser, username: str) -> FollowState:
    """Follow a member. Idempotent; yourself is 400. Allowed while suspended."""
    return profiles.follow(session=session, user=user, username=username)


@router.delete("/users/{username}/follow", response_model=FollowState)
def unfollow_user(session: SessionDep, user: CurrentUser, username: str) -> FollowState:
    """Stop following a member. Idempotent."""
    return profiles.unfollow(session=session, user=user, username=username)


@router.get("/following/activity", response_model=UserCommentsPublic)
def read_following_activity(
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
    skip: Skip = 0,
    limit: Limit = 20,
) -> UserCommentsPublic:
    """Recent visible comments of the people I follow, newest first."""
    return profiles.following_activity(
        session=session, storage=storage, user=user, skip=skip, limit=limit
    )


# --- notifications (my own only) ---


@router.get("/notifications", response_model=NotificationsPublic)
def read_notifications(
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
    skip: Skip = 0,
    limit: Limit = 20,
) -> NotificationsPublic:
    """My notifications, newest first."""
    return notifications.list_notifications(
        session=session, storage=storage, user=user, skip=skip, limit=limit
    )


@router.get("/notifications/unread-count", response_model=UnreadCount)
def read_unread_count(session: SessionDep, user: CurrentUser) -> UnreadCount:
    return notifications.unread_count(session=session, user=user)


@router.post("/notifications/read-all", response_model=UnreadCount)
def read_all_notifications(session: SessionDep, user: CurrentUser) -> UnreadCount:
    return notifications.mark_all_read(session=session, user=user)


@router.post("/notifications/{notification_id}/read", response_model=UnreadCount)
def read_notification(
    session: SessionDep, user: CurrentUser, notification_id: uuid.UUID
) -> UnreadCount:
    """Mark one of my notifications as read; someone else's is a 404."""
    return notifications.mark_read(
        session=session, user=user, notification_id=notification_id
    )


# --- moderation (moderator, admin, superuser) ---


@router.get("/moderation/comments", response_model=ModerationQueue)
def read_moderation_queue(
    session: SessionDep,
    storage: StorageDep,
    _moderator: ModeratorUser,
    queue_filter: Annotated[
        QueueFilter | None,
        Query(alias="filter", description="reported or hidden; omit for both"),
    ] = None,
    skip: Skip = 0,
    limit: Limit = 20,
) -> ModerationQueue:
    """Comments with open reports, plus hidden comments, newest first."""
    return service.moderation_queue(
        session=session,
        storage=storage,
        queue_filter=queue_filter,
        skip=skip,
        limit=limit,
    )


@router.post("/moderation/comments/{comment_id}/hide", response_model=Message)
def hide_comment(
    session: SessionDep, moderator: ModeratorUser, comment_id: uuid.UUID
) -> Message:
    return service.hide_comment(session=session, actor=moderator, comment_id=comment_id)


@router.post("/moderation/comments/{comment_id}/restore", response_model=Message)
def restore_comment(
    session: SessionDep, moderator: ModeratorUser, comment_id: uuid.UUID
) -> Message:
    return service.restore_comment(
        session=session, actor=moderator, comment_id=comment_id
    )


@router.delete("/moderation/comments/{comment_id}", response_model=Message)
def moderator_delete_comment(
    session: SessionDep, moderator: ModeratorUser, comment_id: uuid.UUID
) -> Message:
    """Delete any comment (a placeholder stays when it has replies)."""
    return service.moderator_delete_comment(
        session=session, actor=moderator, comment_id=comment_id
    )


@router.post(
    "/moderation/comments/{comment_id}/resolve-reports", response_model=Message
)
def resolve_comment_reports(
    session: SessionDep, moderator: ModeratorUser, comment_id: uuid.UUID
) -> Message:
    return service.resolve_reports(
        session=session, actor=moderator, comment_id=comment_id
    )


@router.get("/moderation/suspensions", response_model=SuspensionsPublic)
def read_suspensions(
    session: SessionDep,
    storage: StorageDep,
    _moderator: ModeratorUser,
    active_only: bool = True,
    skip: Skip = 0,
    limit: Limit = 20,
) -> SuspensionsPublic:
    return service.list_suspensions(
        session=session,
        storage=storage,
        active_only=active_only,
        skip=skip,
        limit=limit,
    )


@router.post("/moderation/suspensions", response_model=SuspensionPublic)
def create_suspension(
    session: SessionDep,
    storage: StorageDep,
    moderator: ModeratorUser,
    suspension_in: SuspensionCreate,
) -> SuspensionPublic:
    """Suspend a member from commenting, liking and reporting (login still works)."""
    return service.create_suspension(
        session=session, storage=storage, actor=moderator, data=suspension_in
    )


@router.delete(
    "/moderation/suspensions/{suspension_id}", response_model=SuspensionPublic
)
def end_suspension(
    session: SessionDep,
    storage: StorageDep,
    moderator: ModeratorUser,
    suspension_id: uuid.UUID,
) -> SuspensionPublic:
    """End a suspension now (the row stays as history)."""
    return service.end_suspension(
        session=session,
        storage=storage,
        actor=moderator,
        suspension_id=suspension_id,
    )

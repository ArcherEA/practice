"""Request and response schemas of the community module.

Responses never contain an email address: authors are shown as `AuthorPublic`.
"""

import unicodedata
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.modules.community.models import NotificationType, ReportReason

COMMENT_MAX_LENGTH = 5000
TargetType = Literal["post", "page"]


class CommentSort(StrEnum):
    newest = "newest"
    oldest = "oldest"


class CommentState(StrEnum):
    """How a comment is shown. Anything but `visible` is a placeholder."""

    visible = "visible"
    hidden = "hidden"  # hidden by a moderator (kept only because it has replies)
    deleted = "deleted"  # deleted by its author (kept only because it has replies)
    removed = "removed"  # deleted by a moderator (kept only because it has replies)


class QueueFilter(StrEnum):
    reported = "reported"
    hidden = "hidden"


def clean_comment_body(value: str) -> str:
    """Trim, normalise line breaks, and refuse empty / long / control-character text."""
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("Comment cannot be empty")
    if len(text) > COMMENT_MAX_LENGTH:
        raise ValueError(f"Comment is too long (max {COMMENT_MAX_LENGTH} characters)")
    for char in text:
        if char not in "\n\t" and unicodedata.category(char) == "Cc":
            raise ValueError("Comment contains control characters")
    return text


# --- authors ---


class AuthorPublic(SQLModel):
    id: uuid.UUID
    # Lets the UI link to the profile (`/u/<username>`).
    username: str
    # `full_name`, or "Member xxxxxxxx" when the user has none. Never the email.
    display_name: str
    avatar_url: str | None = None


# --- comments ---


class CommentCreate(SQLModel):
    body: str = Field(max_length=4 * COMMENT_MAX_LENGTH)
    parent_id: uuid.UUID | None = Field(
        default=None, description="Top-level comment to reply to (one level only)"
    )

    @field_validator("body")
    @classmethod
    def _check_body(cls, value: str) -> str:
        return clean_comment_body(value)


class CommentUpdate(SQLModel):
    body: str = Field(max_length=4 * COMMENT_MAX_LENGTH)

    @field_validator("body")
    @classmethod
    def _check_body(cls, value: str) -> str:
        return clean_comment_body(value)


class ReplyPublic(SQLModel):
    id: uuid.UUID
    target_type: TargetType
    target_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    # None for placeholders (hidden / deleted / removed) and deleted users.
    author: AuthorPublic | None = None
    # Placeholder text for anything but `visible`.
    body: str
    state: CommentState
    created_at: datetime
    edited_at: datetime | None = None
    like_count: int
    liked_by_me: bool = False
    # Only for the logged-in author while the 15 minute window is open.
    can_edit: bool = False


class CommentPublic(ReplyPublic):
    replies: list[ReplyPublic] = []


class CommentsPublic(SQLModel):
    data: list[CommentPublic]
    # Number of top-level comments (replies come nested inside them).
    count: int
    # The post's like state, so one request renders the whole section.
    # Only set for posts.
    post_like_count: int | None = None
    post_liked_by_me: bool | None = None


class LikeState(SQLModel):
    like_count: int
    liked_by_me: bool


# --- reports ---


class ReportCreate(SQLModel):
    reason: ReportReason
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def _trim_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if any(c not in "\n\t" and unicodedata.category(c) == "Cc" for c in value):
            raise ValueError("Note contains control characters")
        return value or None


class ReportPublic(SQLModel):
    id: uuid.UUID
    reason: ReportReason
    note: str | None = None
    reporter: AuthorPublic | None = None
    created_at: datetime


# --- moderation ---


class CommentTargetPublic(SQLModel):
    """The post or page a comment belongs to, enough to link to it."""

    type: TargetType
    id: uuid.UUID
    title: str
    slug: str


class ModerationComment(SQLModel):
    """A comment with its real body and author, for the moderator queue."""

    id: uuid.UUID
    target_type: TargetType
    target_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    author: AuthorPublic | None = None
    body: str
    state: CommentState
    created_at: datetime
    edited_at: datetime | None = None
    like_count: int
    open_report_count: int
    # Open reports only, oldest first.
    reports: list[ReportPublic]
    # The post or page it belongs to, to link to it.
    target: CommentTargetPublic | None = None


class ModerationQueue(SQLModel):
    data: list[ModerationComment]
    count: int


class SuspensionCreate(SQLModel):
    user_id: uuid.UUID
    until: datetime | None = Field(
        default=None, description="End of the suspension; omit for an indefinite one"
    )
    reason: str | None = Field(default=None, max_length=500)


class SuspensionPublic(SQLModel):
    id: uuid.UUID
    user: AuthorPublic | None = None
    user_id: uuid.UUID
    until: datetime | None = None
    reason: str | None = None
    created_by: AuthorPublic | None = None
    created_at: datetime
    ended_at: datetime | None = None
    active: bool


class SuspensionsPublic(SQLModel):
    data: list[SuspensionPublic]
    count: int


class MySuspension(SQLModel):
    """The logged-in user's own suspension status (for the comment form)."""

    suspended: bool
    until: datetime | None = None
    reason: str | None = None


# --- profiles and follows ---


class ProfilePublic(SQLModel):
    """A member's public profile. Never contains the email address."""

    id: uuid.UUID
    username: str
    display_name: str
    avatar_url: str | None = None
    bio: str | None = None
    joined_at: datetime | None = None
    # Visible comments on published posts and pages.
    comment_count: int
    follower_count: int
    following_count: int
    # Only for logged-in viewers.
    followed_by_me: bool | None = None
    # Only for moderators and above; None for everybody else.
    is_suspended: bool | None = None


class UserCommentPublic(SQLModel):
    id: uuid.UUID
    author: AuthorPublic
    body: str
    parent_id: uuid.UUID | None = None
    created_at: datetime
    like_count: int
    target: CommentTargetPublic


class UserCommentsPublic(SQLModel):
    data: list[UserCommentPublic]
    count: int


class AuthorsPublic(SQLModel):
    data: list[AuthorPublic]
    count: int


class FollowState(SQLModel):
    following: bool
    follower_count: int


# --- notifications ---


class NotificationPublic(SQLModel):
    id: uuid.UUID
    type: NotificationType
    # None when the actor deleted their account.
    actor: AuthorPublic | None = None
    comment_id: uuid.UUID | None = None
    # At most 140 characters; None for follows and when the comment is gone or hidden.
    comment_snippet: str | None = None
    # The post or page to link to; None when it is gone or not published.
    target: CommentTargetPublic | None = None
    created_at: datetime
    read: bool


class NotificationsPublic(SQLModel):
    data: list[NotificationPublic]
    count: int


class UnreadCount(SQLModel):
    unread_count: int

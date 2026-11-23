"""Database tables of the community module (they always exist, even if the module is off).

Nothing here changes a core table: suspensions, like counters and reports live in
their own tables, keyed by user / post / comment ids.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Index, String, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel

from app.models import get_datetime_utc


class CommentStatus(StrEnum):
    visible = "visible"
    hidden = "hidden"


class ReportReason(StrEnum):
    spam = "spam"
    abuse = "abuse"
    other = "other"


class ReportStatus(StrEnum):
    open = "open"
    resolved = "resolved"


class Comment(SQLModel, table=True):
    """A comment on a published post or page (exactly one of `post_id` / `page_id`).

    Two real foreign keys (instead of a polymorphic id) so that deleting a post or page
    deletes its comments in the database, with no code in the content module.
    """

    __tablename__ = "comment"
    __table_args__ = (
        CheckConstraint(
            "(post_id IS NOT NULL AND page_id IS NULL) "
            "OR (post_id IS NULL AND page_id IS NOT NULL)",
            name="ck_comment_one_target",
        ),
        Index("ix_comment_post_created", "post_id", "created_at"),
        Index("ix_comment_page_created", "page_id", "created_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    post_id: uuid.UUID | None = Field(
        default=None, foreign_key="post.id", ondelete="CASCADE"
    )
    page_id: uuid.UUID | None = Field(
        default=None, foreign_key="page.id", ondelete="CASCADE"
    )
    # The author may be deleted later: the comment stays, shown as a deleted user.
    author_id: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL", index=True
    )
    # Null for top-level comments; a top-level comment for replies (one level only).
    parent_id: uuid.UUID | None = Field(
        default=None, foreign_key="comment.id", ondelete="CASCADE", index=True
    )
    # Plain text. The frontend renders it as text, never as HTML.
    body: str = Field(sa_type=Text, nullable=False)
    status: CommentStatus = Field(
        default=CommentStatus.visible,
        sa_type=String(20),
        sa_column_kwargs={"nullable": False, "server_default": "visible"},
        index=True,
    )
    # Soft delete (the comment has replies): body replaced by a placeholder.
    deleted_at: datetime | None = Field(default=None)
    removed_by_moderator: bool = Field(
        default=False, sa_column_kwargs={"server_default": text("false")}
    )
    like_count: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    created_at: datetime = Field(default_factory=get_datetime_utc, index=True)
    edited_at: datetime | None = Field(default=None)


class CommentLike(SQLModel, table=True):
    __tablename__ = "comment_like"

    comment_id: uuid.UUID = Field(
        foreign_key="comment.id", primary_key=True, ondelete="CASCADE"
    )
    user_id: uuid.UUID = Field(
        foreign_key="user.id", primary_key=True, ondelete="CASCADE", index=True
    )
    created_at: datetime = Field(default_factory=get_datetime_utc)


class PostLike(SQLModel, table=True):
    __tablename__ = "post_like"

    post_id: uuid.UUID = Field(
        foreign_key="post.id", primary_key=True, ondelete="CASCADE"
    )
    user_id: uuid.UUID = Field(
        foreign_key="user.id", primary_key=True, ondelete="CASCADE", index=True
    )
    created_at: datetime = Field(default_factory=get_datetime_utc)


class PostLikeCount(SQLModel, table=True):
    """Like counter of a post, kept here so the content module stays unchanged."""

    __tablename__ = "post_like_count"

    post_id: uuid.UUID = Field(
        foreign_key="post.id", primary_key=True, ondelete="CASCADE"
    )
    like_count: int = Field(default=0)


class CommentReport(SQLModel, table=True):
    """One report per user and comment (also after it was resolved)."""

    __tablename__ = "comment_report"
    __table_args__ = (
        UniqueConstraint("comment_id", "reporter_id", name="uq_comment_report_once"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    comment_id: uuid.UUID = Field(
        foreign_key="comment.id", ondelete="CASCADE", index=True
    )
    reporter_id: uuid.UUID = Field(
        foreign_key="user.id", ondelete="CASCADE", index=True
    )
    reason: ReportReason = Field(sa_type=String(20), nullable=False)
    note: str | None = Field(default=None, max_length=500)
    status: ReportStatus = Field(
        default=ReportStatus.open,
        sa_type=String(20),
        sa_column_kwargs={"nullable": False, "server_default": "open"},
        index=True,
    )
    created_at: datetime = Field(default_factory=get_datetime_utc, index=True)
    resolved_at: datetime | None = Field(default=None)
    resolved_by: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )


class CommunitySuspension(SQLModel, table=True):
    """A member barred from commenting, liking and reporting (login is unaffected).

    Active while `ended_at` is null and `until` is null (indefinite) or in the future.
    """

    __tablename__ = "community_suspension"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    until: datetime | None = Field(default=None)
    reason: str | None = Field(default=None, max_length=500)
    created_by: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )
    created_at: datetime = Field(default_factory=get_datetime_utc)
    ended_at: datetime | None = Field(default=None)

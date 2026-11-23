"""Database tables of the content module (they always exist, even if the module is off)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

from app.models import get_datetime_utc

if TYPE_CHECKING:
    from app.models import User


class ContentStatus(StrEnum):
    draft = "draft"
    published = "published"


class PostTag(SQLModel, table=True):
    """Many-to-many link between posts and tags."""

    __tablename__ = "post_tag"

    post_id: uuid.UUID = Field(
        foreign_key="post.id", primary_key=True, ondelete="CASCADE"
    )
    tag_id: uuid.UUID = Field(
        foreign_key="tag.id", primary_key=True, ondelete="CASCADE", index=True
    )


class Category(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(unique=True, index=True, max_length=80)
    description: str | None = Field(default=None, max_length=500)


class Tag(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(unique=True, index=True, max_length=80)


class Post(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=255)
    slug: str = Field(unique=True, index=True, max_length=80)
    excerpt: str | None = Field(default=None, max_length=500)
    # Tiptap/ProseMirror JSON, validated by `body.sanitize_body` before it is stored.
    body: dict[str, object] = Field(sa_type=JSONB, nullable=False)
    cover_file_id: uuid.UUID | None = Field(
        default=None, foreign_key="file.id", ondelete="SET NULL"
    )
    category_id: uuid.UUID | None = Field(
        default=None, foreign_key="category.id", ondelete="SET NULL", index=True
    )
    status: ContentStatus = Field(
        default=ContentStatus.draft,
        sa_type=String(20),
        sa_column_kwargs={"nullable": False, "server_default": "draft"},
        index=True,
    )
    published_at: datetime | None = Field(default=None, index=True)
    author_id: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL", index=True
    )
    seo_title: str | None = Field(default=None, max_length=255)
    seo_description: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=get_datetime_utc)
    updated_at: datetime = Field(default_factory=get_datetime_utc)

    # Loaded together with the post ("selectin") so lists don't query per row.
    # SQLAlchemy cannot resolve "X | None" strings, hence Optional[...].
    category: Optional["Category"] = Relationship(  # noqa: UP037, UP045
        sa_relationship_kwargs={"lazy": "selectin"}
    )
    author: Optional["User"] = Relationship(  # noqa: UP037, UP045
        sa_relationship_kwargs={"lazy": "selectin"}
    )
    tags: list[Tag] = Relationship(
        link_model=PostTag, sa_relationship_kwargs={"lazy": "selectin"}
    )


class Page(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=255)
    slug: str = Field(unique=True, index=True, max_length=80)
    body: dict[str, object] = Field(sa_type=JSONB, nullable=False)
    status: ContentStatus = Field(
        default=ContentStatus.draft,
        sa_type=String(20),
        sa_column_kwargs={"nullable": False, "server_default": "draft"},
        index=True,
    )
    published_at: datetime | None = Field(default=None)
    author_id: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL", index=True
    )
    seo_title: str | None = Field(default=None, max_length=255)
    seo_description: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=get_datetime_utc)
    updated_at: datetime = Field(default_factory=get_datetime_utc)

    author: Optional["User"] = Relationship(  # noqa: UP037, UP045
        sa_relationship_kwargs={"lazy": "selectin"}
    )

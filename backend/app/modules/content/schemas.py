"""Request and response schemas of the content module."""

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from app.core.richtext import JsonDict, empty_body
from app.modules.content.models import ContentStatus

# --- categories and tags ---


class CategoryCreate(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="Optional; generated from the name when omitted",
    )
    description: str | None = Field(default=None, max_length=500)


class CategoryUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)


class CategoryPublic(SQLModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None


class CategoriesPublic(SQLModel):
    data: list[CategoryPublic]
    count: int


class TagCreate(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=80)


class TagUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=80)


class TagPublic(SQLModel):
    id: uuid.UUID
    name: str
    slug: str


class TagsPublic(SQLModel):
    data: list[TagPublic]
    count: int


# --- posts ---


class PostCreate(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="Optional; generated from the title when omitted. Normalized and made unique.",
    )
    excerpt: str | None = Field(default=None, max_length=500)
    body: JsonDict = Field(
        default_factory=empty_body,
        description="Tiptap JSON document; see docs/ARCHITECTURE.md for the allow-list",
    )
    cover_file_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    seo_title: str | None = Field(default=None, max_length=255)
    seo_description: str | None = Field(default=None, max_length=500)


class PostUpdate(SQLModel):
    """Only the fields you send are changed; send null to clear nullable ones."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    excerpt: str | None = Field(default=None, max_length=500)
    body: JsonDict | None = None
    cover_file_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] | None = Field(default=None, max_length=30)
    seo_title: str | None = Field(default=None, max_length=255)
    seo_description: str | None = Field(default=None, max_length=500)


class PostSummary(SQLModel):
    """A post without its body, for lists."""

    id: uuid.UUID
    title: str
    slug: str
    excerpt: str | None = None
    cover_file_id: uuid.UUID | None = None
    cover_url: str | None = Field(
        default=None, description="Stable URL of the cover image (redirects to storage)"
    )
    status: ContentStatus
    published_at: datetime | None = None
    author_id: uuid.UUID | None = None
    author_name: str | None = None
    category: CategoryPublic | None = None
    tags: list[TagPublic]
    created_at: datetime
    updated_at: datetime


class PostPublic(PostSummary):
    body: JsonDict = Field(
        description="Tiptap JSON; image nodes carry a resolved attrs.src"
    )
    seo_title: str | None = None
    seo_description: str | None = None


class PostsPublic(SQLModel):
    data: list[PostSummary]
    count: int


# --- pages ---


class PageCreate(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    body: JsonDict = Field(default_factory=empty_body)
    seo_title: str | None = Field(default=None, max_length=255)
    seo_description: str | None = Field(default=None, max_length=500)


class PageUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    body: JsonDict | None = None
    seo_title: str | None = Field(default=None, max_length=255)
    seo_description: str | None = Field(default=None, max_length=500)


class PageSummary(SQLModel):
    id: uuid.UUID
    title: str
    slug: str
    status: ContentStatus
    published_at: datetime | None = None
    author_id: uuid.UUID | None = None
    author_name: str | None = None
    created_at: datetime
    updated_at: datetime


class PagePublic(PageSummary):
    body: JsonDict
    seo_title: str | None = None
    seo_description: str | None = None


class PagesPublic(SQLModel):
    data: list[PageSummary]
    count: int

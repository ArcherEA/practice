"""Content service: slugs, body checks, publishing, queries and response building.

Routes stay thin and call these functions. Errors are `HTTPException`s, as in the
rest of the API.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, func, select
from sqlmodel.sql.expression import SelectOfScalar

from app.core.config import settings
from app.core.storage import is_inline_content_type
from app.models import File, FileStatus, User, get_datetime_utc
from app.modules.content import body as body_rules
from app.modules.content.body import JsonDict
from app.modules.content.models import (
    Category,
    ContentStatus,
    Page,
    Post,
    PostTag,
    Tag,
)
from app.modules.content.schemas import (
    CategoryCreate,
    CategoryPublic,
    CategoryUpdate,
    PageCreate,
    PagePublic,
    PageSummary,
    PageUpdate,
    PostCreate,
    PostPublic,
    PostSummary,
    PostUpdate,
    TagCreate,
    TagPublic,
    TagUpdate,
)
from app.modules.content.slugs import unique_slug

Sluggable = Post | Page | Category | Tag


# --- slugs ---


def make_slug(
    session: Session,
    model: type[Sluggable],
    text: str,
    *,
    exclude_id: uuid.UUID | None = None,
) -> str:
    """Normalized slug for `text`, unique in `model`'s table (`-2`, `-3`... on clashes)."""

    def taken(candidate: str) -> bool:
        statement = select(model.id).where(model.slug == candidate)
        if exclude_id is not None:
            statement = statement.where(model.id != exclude_id)
        return session.exec(statement).first() is not None

    return unique_slug(text, taken)


def _commit(session: Session) -> None:
    """Commit; a lost slug race (unique constraint) becomes 409 instead of 500."""
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Slug already in use, please try again"
        ) from None


# --- body and files ---


def image_url(file_id: uuid.UUID | str) -> str:
    """Stable, non-expiring URL of a public image (redirects to storage)."""
    return f"{settings.API_V1_STR}/files/{file_id}/content"


def _check_image_files(session: Session, file_ids: set[uuid.UUID]) -> None:
    """Every id must be a ready, public image file (any owner)."""
    if not file_ids:
        return
    found = {
        f.id: f
        for f in session.exec(select(File).where(col(File.id).in_(file_ids))).all()
    }
    for file_id in sorted(file_ids, key=str):
        file = found.get(file_id)
        if file is None:
            raise HTTPException(
                status_code=422, detail=f"Image file {file_id} not found"
            )
        if (
            file.status != FileStatus.ready
            or not file.public
            or not is_inline_content_type(file.content_type)
        ):
            raise HTTPException(
                status_code=422,
                detail=f"File {file_id} must be a ready, public JPEG, PNG, WebP or GIF image",
            )


def clean_body(session: Session, raw: JsonDict) -> JsonDict:
    """Validate the body (allow-list + referenced image files) and return the cleaned copy."""
    try:
        result = body_rules.sanitize_body(raw)
    except body_rules.BodyValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid body: {exc}") from None
    _check_image_files(session, result.image_file_ids)
    return result.body


def _check_cover(session: Session, cover_file_id: uuid.UUID | None) -> None:
    if cover_file_id is not None:
        _check_image_files(session, {cover_file_id})


def resolved_body(raw: JsonDict) -> JsonDict:
    """Body for responses: image nodes get ``attrs.src`` (the stable content URL)."""
    return body_rules.with_image_urls(raw, image_url("{file_id}"))


# --- lookups ---


def _get_or_404[T: (Post, Page, Category, Tag)](
    session: Session, model: type[T], item_id: uuid.UUID
) -> T:
    item = session.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return item


def get_post(session: Session, post_id: uuid.UUID) -> Post:
    return _get_or_404(session, Post, post_id)


def get_page(session: Session, page_id: uuid.UUID) -> Page:
    return _get_or_404(session, Page, page_id)


def get_published_post(session: Session, slug: str) -> Post:
    post = session.exec(
        select(Post).where(Post.slug == slug, Post.status == ContentStatus.published)
    ).first()
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


def get_published_page(session: Session, slug: str) -> Page:
    page = session.exec(
        select(Page).where(Page.slug == slug, Page.status == ContentStatus.published)
    ).first()
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


def _count(
    session: Session, statement: SelectOfScalar[Post] | SelectOfScalar[Page]
) -> int:
    return session.exec(select(func.count()).select_from(statement.subquery())).one()


def list_posts(
    session: Session,
    *,
    skip: int,
    limit: int,
    published_only: bool,
    category_slug: str | None = None,
    tag_slug: str | None = None,
    status: ContentStatus | None = None,
    query: str | None = None,
) -> tuple[Sequence[Post], int]:
    statement = select(Post)
    if published_only:
        statement = statement.where(Post.status == ContentStatus.published)
    if status is not None:
        statement = statement.where(Post.status == status)
    if category_slug:
        statement = statement.where(
            col(Post.category_id).in_(
                select(Category.id).where(Category.slug == category_slug)
            )
        )
    if tag_slug:
        statement = statement.where(
            col(Post.id).in_(
                select(PostTag.post_id)
                .join(Tag, col(Tag.id) == col(PostTag.tag_id))
                .where(Tag.slug == tag_slug)
            )
        )
    if query:
        statement = statement.where(col(Post.title).ilike(f"%{_escape_like(query)}%"))
    count = _count(session, statement)
    order = (
        col(Post.published_at).desc() if published_only else col(Post.created_at).desc()
    )
    rows = session.exec(
        statement.order_by(order, col(Post.id)).offset(skip).limit(limit)
    )
    return rows.all(), count


def list_pages(
    session: Session,
    *,
    skip: int,
    limit: int,
    status: ContentStatus | None = None,
    query: str | None = None,
) -> tuple[Sequence[Page], int]:
    statement = select(Page)
    if status is not None:
        statement = statement.where(Page.status == status)
    if query:
        statement = statement.where(col(Page.title).ilike(f"%{_escape_like(query)}%"))
    count = _count(session, statement)
    rows = session.exec(
        statement.order_by(col(Page.title), col(Page.id)).offset(skip).limit(limit)
    )
    return rows.all(), count


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --- tags and categories on posts ---


def _load_tags(session: Session, tag_ids: list[uuid.UUID]) -> list[Tag]:
    unique_ids = list(dict.fromkeys(tag_ids))
    if not unique_ids:
        return []
    found = {
        t.id: t for t in session.exec(select(Tag).where(col(Tag.id).in_(unique_ids)))
    }
    missing = [str(i) for i in unique_ids if i not in found]
    if missing:
        raise HTTPException(
            status_code=422, detail=f"Unknown tag id(s): {', '.join(missing)}"
        )
    return [found[i] for i in unique_ids]


def _check_category(session: Session, category_id: uuid.UUID | None) -> None:
    if category_id is not None and session.get(Category, category_id) is None:
        raise HTTPException(status_code=422, detail="Unknown category id")


# --- posts ---


def create_post(*, session: Session, user: User, data: PostCreate) -> Post:
    body = clean_body(session, data.body)
    _check_cover(session, data.cover_file_id)
    _check_category(session, data.category_id)
    tags = _load_tags(session, data.tag_ids)
    post = Post(
        title=data.title,
        slug=make_slug(session, Post, data.slug or data.title),
        excerpt=data.excerpt,
        body=body,
        cover_file_id=data.cover_file_id,
        category_id=data.category_id,
        author_id=user.id,
        seo_title=data.seo_title,
        seo_description=data.seo_description,
        tags=tags,
    )
    session.add(post)
    _commit(session)
    session.refresh(post)
    return post


def update_post(*, session: Session, post: Post, data: PostUpdate) -> Post:
    fields = data.model_dump(exclude_unset=True)
    if fields.get("title") is not None:
        post.title = fields["title"]
    if fields.get("slug") is not None:
        post.slug = make_slug(session, Post, fields["slug"], exclude_id=post.id)
    if fields.get("body") is not None:
        post.body = clean_body(session, fields["body"])
    if "cover_file_id" in fields:
        _check_cover(session, data.cover_file_id)
        post.cover_file_id = data.cover_file_id
    if "category_id" in fields:
        _check_category(session, data.category_id)
        post.category_id = data.category_id
    if fields.get("tag_ids") is not None:
        post.tags = _load_tags(session, fields["tag_ids"])
    for name in ("excerpt", "seo_title", "seo_description"):
        if name in fields:
            setattr(post, name, fields[name])
    post.updated_at = get_datetime_utc()
    session.add(post)
    _commit(session)
    session.refresh(post)
    return post


# --- pages ---


def create_page(*, session: Session, user: User, data: PageCreate) -> Page:
    page = Page(
        title=data.title,
        slug=make_slug(session, Page, data.slug or data.title),
        body=clean_body(session, data.body),
        author_id=user.id,
        seo_title=data.seo_title,
        seo_description=data.seo_description,
    )
    session.add(page)
    _commit(session)
    session.refresh(page)
    return page


def update_page(*, session: Session, page: Page, data: PageUpdate) -> Page:
    fields = data.model_dump(exclude_unset=True)
    if fields.get("title") is not None:
        page.title = fields["title"]
    if fields.get("slug") is not None:
        page.slug = make_slug(session, Page, fields["slug"], exclude_id=page.id)
    if fields.get("body") is not None:
        page.body = clean_body(session, fields["body"])
    for name in ("seo_title", "seo_description"):
        if name in fields:
            setattr(page, name, fields[name])
    page.updated_at = get_datetime_utc()
    session.add(page)
    _commit(session)
    session.refresh(page)
    return page


# --- publishing and deleting (posts and pages) ---


def set_status[T: (Post, Page)](
    *, session: Session, item: T, status: Literal["published", "draft"]
) -> T:
    """Publish (sets `published_at` on the first publish only) or return to draft."""
    if status == "published":
        item.status = ContentStatus.published
        if item.published_at is None:
            item.published_at = get_datetime_utc()
    else:
        item.status = ContentStatus.draft
    item.updated_at = get_datetime_utc()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def delete_item(*, session: Session, item: Post | Page | Category | Tag) -> None:
    """Delete only the row: image files stay (they may be reused); posts lose a
    deleted category / tag through the foreign keys (SET NULL / CASCADE)."""
    session.delete(item)
    session.commit()


# --- categories and tags ---


def create_category(*, session: Session, data: CategoryCreate) -> Category:
    category = Category(
        name=data.name,
        slug=make_slug(session, Category, data.slug or data.name),
        description=data.description,
    )
    session.add(category)
    _commit(session)
    session.refresh(category)
    return category


def update_category(
    *, session: Session, category: Category, data: CategoryUpdate
) -> Category:
    fields = data.model_dump(exclude_unset=True)
    if fields.get("name") is not None:
        category.name = fields["name"]
    if fields.get("slug") is not None:
        category.slug = make_slug(
            session, Category, fields["slug"], exclude_id=category.id
        )
    if "description" in fields:
        category.description = fields["description"]
    session.add(category)
    _commit(session)
    session.refresh(category)
    return category


def create_tag(*, session: Session, data: TagCreate) -> Tag:
    tag = Tag(name=data.name, slug=make_slug(session, Tag, data.slug or data.name))
    session.add(tag)
    _commit(session)
    session.refresh(tag)
    return tag


def update_tag(*, session: Session, tag: Tag, data: TagUpdate) -> Tag:
    fields = data.model_dump(exclude_unset=True)
    if fields.get("name") is not None:
        tag.name = fields["name"]
    if fields.get("slug") is not None:
        tag.slug = make_slug(session, Tag, fields["slug"], exclude_id=tag.id)
    session.add(tag)
    _commit(session)
    session.refresh(tag)
    return tag


def get_category(session: Session, category_id: uuid.UUID) -> Category:
    return _get_or_404(session, Category, category_id)


def get_tag(session: Session, tag_id: uuid.UUID) -> Tag:
    return _get_or_404(session, Tag, tag_id)


def list_categories(session: Session) -> Sequence[Category]:
    return session.exec(select(Category).order_by(col(Category.name))).all()


def list_tags(session: Session) -> Sequence[Tag]:
    return session.exec(select(Tag).order_by(col(Tag.name))).all()


# --- response building ---


def _author_name(item: Post | Page) -> str | None:
    return (item.author.full_name or None) if item.author else None


def to_post_summary(post: Post) -> PostSummary:
    return PostSummary(
        id=post.id,
        title=post.title,
        slug=post.slug,
        excerpt=post.excerpt,
        cover_file_id=post.cover_file_id,
        cover_url=image_url(post.cover_file_id) if post.cover_file_id else None,
        status=post.status,
        published_at=post.published_at,
        author_id=post.author_id,
        author_name=_author_name(post),
        category=(
            CategoryPublic.model_validate(post.category) if post.category else None
        ),
        tags=[TagPublic.model_validate(t) for t in post.tags],
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


def to_post_public(post: Post) -> PostPublic:
    summary = to_post_summary(post)
    return PostPublic(
        **summary.model_dump(),
        body=resolved_body(post.body),
        seo_title=post.seo_title,
        seo_description=post.seo_description,
    )


def to_page_summary(page: Page) -> PageSummary:
    return PageSummary(
        id=page.id,
        title=page.title,
        slug=page.slug,
        status=page.status,
        published_at=page.published_at,
        author_id=page.author_id,
        author_name=_author_name(page),
        created_at=page.created_at,
        updated_at=page.updated_at,
    )


def to_page_public(page: Page) -> PagePublic:
    summary = to_page_summary(page)
    return PagePublic(
        **summary.model_dump(),
        body=resolved_body(page.body),
        seo_title=page.seo_title,
        seo_description=page.seo_description,
    )


ARCHIVE_LIMIT = 1000


def list_archive(session: Session) -> list[tuple[str, str, datetime]]:
    """(title, slug, published_at) of published posts, newest first (timeline)."""
    rows = session.exec(
        select(Post.title, Post.slug, Post.published_at)
        .where(Post.status == ContentStatus.published)
        .order_by(col(Post.published_at).desc(), col(Post.id))
        .limit(ARCHIVE_LIMIT)
    ).all()
    return [
        (title, slug, published_at)
        for title, slug, published_at in rows
        if published_at
    ]

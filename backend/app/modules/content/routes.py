"""Content module API, mounted at /api/v1/content.

Public routes (no auth) only ever return *published* content. Everything under
`/manage` needs the editor role (editor, admin or superuser; not moderator).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import RequireEditor, SessionDep, require_role
from app.core.roles import UserRole
from app.models import Message, User
from app.modules.content import service
from app.modules.content.models import ContentStatus
from app.modules.content.schemas import (
    CategoriesPublic,
    CategoryCreate,
    CategoryPublic,
    CategoryUpdate,
    PageCreate,
    PagePublic,
    PagesPublic,
    PageUpdate,
    PostCreate,
    PostPublic,
    PostsPublic,
    PostUpdate,
    TagCreate,
    TagPublic,
    TagsPublic,
    TagUpdate,
)

router = APIRouter(prefix="/content", tags=["content"])

EditorUser = Annotated[User, Depends(require_role(UserRole.editor))]
Skip = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]

# --- public (published content only) ---


@router.get("/posts", response_model=PostsPublic)
def read_published_posts(
    session: SessionDep,
    skip: Skip = 0,
    limit: Limit = 20,
    category: Annotated[str | None, Query(description="Category slug")] = None,
    tag: Annotated[str | None, Query(description="Tag slug")] = None,
) -> PostsPublic:
    """Published posts, newest first. Filter by category slug and/or tag slug."""
    posts, count = service.list_posts(
        session,
        skip=skip,
        limit=limit,
        published_only=True,
        category_slug=category,
        tag_slug=tag,
    )
    return PostsPublic(data=[service.to_post_summary(p) for p in posts], count=count)


@router.get("/posts/{slug}", response_model=PostPublic)
def read_published_post(session: SessionDep, slug: str) -> PostPublic:
    """A published post by slug (404 for drafts and unknown slugs)."""
    return service.to_post_public(service.get_published_post(session, slug))


@router.get("/pages", response_model=PagesPublic)
def read_published_pages(
    session: SessionDep, skip: Skip = 0, limit: Limit = 50
) -> PagesPublic:
    """Published pages by title (no body) — for the public site menu."""
    pages, count = service.list_pages(
        session, skip=skip, limit=limit, status=ContentStatus.published
    )
    return PagesPublic(data=[service.to_page_summary(p) for p in pages], count=count)


@router.get("/pages/{slug}", response_model=PagePublic)
def read_published_page(session: SessionDep, slug: str) -> PagePublic:
    """A published page by slug (404 for drafts and unknown slugs)."""
    return service.to_page_public(service.get_published_page(session, slug))


@router.get("/categories", response_model=CategoriesPublic)
def read_categories(session: SessionDep) -> CategoriesPublic:
    categories = service.list_categories(session)
    return CategoriesPublic(
        data=[CategoryPublic.model_validate(c) for c in categories],
        count=len(categories),
    )


@router.get("/tags", response_model=TagsPublic)
def read_tags(session: SessionDep) -> TagsPublic:
    tags = service.list_tags(session)
    return TagsPublic(data=[TagPublic.model_validate(t) for t in tags], count=len(tags))


# --- editor: posts ---


@router.get("/manage/posts", dependencies=[RequireEditor], response_model=PostsPublic)
def read_manage_posts(
    session: SessionDep,
    skip: Skip = 0,
    limit: Limit = 20,
    status: ContentStatus | None = None,
    q: Annotated[str | None, Query(description="Title contains")] = None,
    category: Annotated[str | None, Query(description="Category slug")] = None,
    tag: Annotated[str | None, Query(description="Tag slug")] = None,
) -> PostsPublic:
    """All posts including drafts, newest first (editor)."""
    posts, count = service.list_posts(
        session,
        skip=skip,
        limit=limit,
        published_only=False,
        category_slug=category,
        tag_slug=tag,
        status=status,
        query=q,
    )
    return PostsPublic(data=[service.to_post_summary(p) for p in posts], count=count)


@router.post("/manage/posts", response_model=PostPublic)
def create_manage_post(
    session: SessionDep, user: EditorUser, post_in: PostCreate
) -> PostPublic:
    """Create a draft post. The author is the current user."""
    post = service.create_post(session=session, user=user, data=post_in)
    return service.to_post_public(post)


@router.get(
    "/manage/posts/{post_id}", dependencies=[RequireEditor], response_model=PostPublic
)
def read_manage_post(session: SessionDep, post_id: uuid.UUID) -> PostPublic:
    return service.to_post_public(service.get_post(session, post_id))


@router.put(
    "/manage/posts/{post_id}", dependencies=[RequireEditor], response_model=PostPublic
)
def update_manage_post(
    session: SessionDep, post_id: uuid.UUID, post_in: PostUpdate
) -> PostPublic:
    """Partial update: only the fields you send change."""
    post = service.get_post(session, post_id)
    return service.to_post_public(
        service.update_post(session=session, post=post, data=post_in)
    )


@router.post(
    "/manage/posts/{post_id}/publish",
    dependencies=[RequireEditor],
    response_model=PostPublic,
)
def publish_manage_post(session: SessionDep, post_id: uuid.UUID) -> PostPublic:
    post = service.get_post(session, post_id)
    return service.to_post_public(
        service.set_status(session=session, item=post, status="published")
    )


@router.post(
    "/manage/posts/{post_id}/unpublish",
    dependencies=[RequireEditor],
    response_model=PostPublic,
)
def unpublish_manage_post(session: SessionDep, post_id: uuid.UUID) -> PostPublic:
    post = service.get_post(session, post_id)
    return service.to_post_public(
        service.set_status(session=session, item=post, status="draft")
    )


@router.delete(
    "/manage/posts/{post_id}", dependencies=[RequireEditor], response_model=Message
)
def delete_manage_post(session: SessionDep, post_id: uuid.UUID) -> Message:
    service.delete_item(session=session, item=service.get_post(session, post_id))
    return Message(message="Post deleted successfully")


# --- editor: pages ---


@router.get("/manage/pages", dependencies=[RequireEditor], response_model=PagesPublic)
def read_manage_pages(
    session: SessionDep,
    skip: Skip = 0,
    limit: Limit = 20,
    status: ContentStatus | None = None,
    q: Annotated[str | None, Query(description="Title contains")] = None,
) -> PagesPublic:
    """All pages including drafts, by title (editor)."""
    pages, count = service.list_pages(
        session, skip=skip, limit=limit, status=status, query=q
    )
    return PagesPublic(data=[service.to_page_summary(p) for p in pages], count=count)


@router.post("/manage/pages", response_model=PagePublic)
def create_manage_page(
    session: SessionDep, user: EditorUser, page_in: PageCreate
) -> PagePublic:
    page = service.create_page(session=session, user=user, data=page_in)
    return service.to_page_public(page)


@router.get(
    "/manage/pages/{page_id}", dependencies=[RequireEditor], response_model=PagePublic
)
def read_manage_page(session: SessionDep, page_id: uuid.UUID) -> PagePublic:
    return service.to_page_public(service.get_page(session, page_id))


@router.put(
    "/manage/pages/{page_id}", dependencies=[RequireEditor], response_model=PagePublic
)
def update_manage_page(
    session: SessionDep, page_id: uuid.UUID, page_in: PageUpdate
) -> PagePublic:
    page = service.get_page(session, page_id)
    return service.to_page_public(
        service.update_page(session=session, page=page, data=page_in)
    )


@router.post(
    "/manage/pages/{page_id}/publish",
    dependencies=[RequireEditor],
    response_model=PagePublic,
)
def publish_manage_page(session: SessionDep, page_id: uuid.UUID) -> PagePublic:
    page = service.get_page(session, page_id)
    return service.to_page_public(
        service.set_status(session=session, item=page, status="published")
    )


@router.post(
    "/manage/pages/{page_id}/unpublish",
    dependencies=[RequireEditor],
    response_model=PagePublic,
)
def unpublish_manage_page(session: SessionDep, page_id: uuid.UUID) -> PagePublic:
    page = service.get_page(session, page_id)
    return service.to_page_public(
        service.set_status(session=session, item=page, status="draft")
    )


@router.delete(
    "/manage/pages/{page_id}", dependencies=[RequireEditor], response_model=Message
)
def delete_manage_page(session: SessionDep, page_id: uuid.UUID) -> Message:
    service.delete_item(session=session, item=service.get_page(session, page_id))
    return Message(message="Page deleted successfully")


# --- editor: categories ---


@router.post(
    "/manage/categories", dependencies=[RequireEditor], response_model=CategoryPublic
)
def create_manage_category(
    session: SessionDep, category_in: CategoryCreate
) -> CategoryPublic:
    return CategoryPublic.model_validate(
        service.create_category(session=session, data=category_in)
    )


@router.put(
    "/manage/categories/{category_id}",
    dependencies=[RequireEditor],
    response_model=CategoryPublic,
)
def update_manage_category(
    session: SessionDep, category_id: uuid.UUID, category_in: CategoryUpdate
) -> CategoryPublic:
    category = service.get_category(session, category_id)
    return CategoryPublic.model_validate(
        service.update_category(session=session, category=category, data=category_in)
    )


@router.delete(
    "/manage/categories/{category_id}",
    dependencies=[RequireEditor],
    response_model=Message,
)
def delete_manage_category(session: SessionDep, category_id: uuid.UUID) -> Message:
    """Delete a category; its posts simply end up without one."""
    service.delete_item(
        session=session, item=service.get_category(session, category_id)
    )
    return Message(message="Category deleted successfully")


# --- editor: tags ---


@router.post("/manage/tags", dependencies=[RequireEditor], response_model=TagPublic)
def create_manage_tag(session: SessionDep, tag_in: TagCreate) -> TagPublic:
    return TagPublic.model_validate(service.create_tag(session=session, data=tag_in))


@router.put(
    "/manage/tags/{tag_id}", dependencies=[RequireEditor], response_model=TagPublic
)
def update_manage_tag(
    session: SessionDep, tag_id: uuid.UUID, tag_in: TagUpdate
) -> TagPublic:
    tag = service.get_tag(session, tag_id)
    return TagPublic.model_validate(
        service.update_tag(session=session, tag=tag, data=tag_in)
    )


@router.delete(
    "/manage/tags/{tag_id}", dependencies=[RequireEditor], response_model=Message
)
def delete_manage_tag(session: SessionDep, tag_id: uuid.UUID) -> Message:
    """Delete a tag; it is removed from all posts."""
    service.delete_item(session=session, item=service.get_tag(session, tag_id))
    return Message(message="Tag deleted successfully")

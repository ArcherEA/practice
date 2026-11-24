"""Commerce module API, mounted at /api/v1/commerce.

Public routes (no auth) only ever return *published* products. The admin API lives
under `/commerce/admin` (see `admin_routes.py`).
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import SessionDep
from app.modules.commerce import service
from app.modules.commerce.admin_routes import router as admin_router
from app.modules.commerce.models import ProductType
from app.modules.commerce.schemas import (
    ProductCategoriesPublic,
    ProductDetail,
    ProductsPublic,
    StoreConfig,
)

router = APIRouter(prefix="/commerce", tags=["commerce"])
router.include_router(admin_router)

Skip = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]
CurrencyQuery = Annotated[
    str | None,
    Query(description="Currency code from the store's list; default: store default"),
]


@router.get("/config", response_model=StoreConfig)
def read_store_config() -> StoreConfig:
    """Currencies (with minor-unit exponent), default currency and timezone of the store."""
    return service.store_config()


@router.get("/categories", response_model=ProductCategoriesPublic)
def read_categories(session: SessionDep) -> ProductCategoriesPublic:
    """Categories that have at least one published product."""
    categories = service.public_categories(session)
    return ProductCategoriesPublic(data=categories, count=len(categories))


@router.get("/products", response_model=ProductsPublic)
def read_published_products(
    session: SessionDep,
    skip: Skip = 0,
    limit: Limit = 20,
    category: Annotated[str | None, Query(description="Category slug")] = None,
    type: ProductType | None = None,  # noqa: A002 - the query parameter is called `type`
    currency: CurrencyQuery = None,
) -> ProductsPublic:
    """Published products, newest first, with the lowest price in `currency`."""
    items, count = service.list_products_public(
        session,
        skip=skip,
        limit=limit,
        currency=service.public_currency(currency),
        category_slug=category,
        type_=type,
    )
    return ProductsPublic(data=items, count=count)


@router.get("/products/{slug}", response_model=ProductDetail)
def read_published_product(
    session: SessionDep, slug: str, currency: CurrencyQuery = None
) -> ProductDetail:
    """A published product with its active variants, prices in `currency`, availability and slots."""
    chosen = service.public_currency(currency)
    product = service.get_published_product(session, slug)
    return service.to_product_detail(session, product, chosen)

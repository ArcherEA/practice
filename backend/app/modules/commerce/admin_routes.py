"""Commerce admin API, mounted at /api/v1/commerce/admin (admin or superuser only).

Moderators, editors and members get 403; the catalog is managed by admins only.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, RequireAdmin, SessionDep, StorageDep
from app.core import files as file_service
from app.core.config import settings
from app.models import (
    FileCreate,
    FilePublic,
    Message,
    UploadTicket,
)
from app.modules.commerce import service
from app.modules.commerce.models import ProductStatus, ProductType
from app.modules.commerce.schemas import (
    OptionCreate,
    OptionPublic,
    OptionUpdate,
    PriceAdmin,
    PriceSet,
    ProductAdmin,
    ProductCategoriesPublic,
    ProductCategoryCreate,
    ProductCategoryPublic,
    ProductCategoryUpdate,
    ProductCreate,
    ProductsAdminSummary,
    ProductUpdate,
    SlotAdmin,
    SlotCreate,
    SlotsAdmin,
    SlotUpdate,
    VariantAdmin,
    VariantCreate,
    VariantUpdate,
)

router = APIRouter(prefix="/admin", dependencies=[RequireAdmin])

Skip = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]

# --- product files (private downloads, larger cap than member uploads) ---


@router.post("/files", response_model=UploadTicket)
def admin_create_product_file_upload(
    session: SessionDep,
    storage: StorageDep,
    current_user: AdminUser,
    file_in: FileCreate,
) -> UploadTicket:
    """
    Reserve a **private** product file and get a presigned PUT URL (same flow as
    `POST /files/`, but up to `PRODUCT_FILE_MAX_BYTES` and not counted against the
    per-user quota). Upload the bytes, then call `POST /commerce/admin/files/{id}/confirm`.
    """
    private = file_in.model_copy(update={"public": False})
    return file_service.create_upload(
        session=session,
        storage=storage,
        user=current_user,
        data=private,
        max_bytes=settings.PRODUCT_FILE_MAX_BYTES,
        enforce_user_limits=False,
    )


@router.post("/files/{file_id}/confirm", response_model=FilePublic)
def admin_confirm_product_file_upload(
    session: SessionDep,
    storage: StorageDep,
    current_user: AdminUser,
    file_id: uuid.UUID,
) -> FilePublic:
    """Verify the uploaded object against `PRODUCT_FILE_MAX_BYTES` and mark it ready."""
    file = service.get_own_pending_product_file(session, current_user, file_id)
    confirmed = file_service.confirm_upload(
        session=session,
        storage=storage,
        file=file,
        max_bytes=settings.PRODUCT_FILE_MAX_BYTES,
    )
    return FilePublic.model_validate(confirmed)


# --- categories ---


@router.get("/categories", response_model=ProductCategoriesPublic)
def admin_read_categories(session: SessionDep) -> ProductCategoriesPublic:
    categories = service.list_categories(session)
    return ProductCategoriesPublic(
        data=[ProductCategoryPublic.model_validate(c) for c in categories],
        count=len(categories),
    )


@router.post("/categories", response_model=ProductCategoryPublic)
def admin_create_category(
    session: SessionDep, data: ProductCategoryCreate
) -> ProductCategoryPublic:
    return ProductCategoryPublic.model_validate(service.create_category(session, data))


@router.patch("/categories/{category_id}", response_model=ProductCategoryPublic)
def admin_update_category(
    session: SessionDep, category_id: uuid.UUID, data: ProductCategoryUpdate
) -> ProductCategoryPublic:
    category = service.get_category(session, category_id)
    return ProductCategoryPublic.model_validate(
        service.update_category(session, category, data)
    )


@router.delete("/categories/{category_id}", response_model=Message)
def admin_delete_category(session: SessionDep, category_id: uuid.UUID) -> Message:
    """Delete a category; its products stay, without a category."""
    service.delete_category(session, service.get_category(session, category_id))
    return Message(message="Category deleted successfully")


# --- products ---


@router.get("/products", response_model=ProductsAdminSummary)
def admin_read_products(
    session: SessionDep,
    skip: Skip = 0,
    limit: Limit = 20,
    status: ProductStatus | None = None,
    type: ProductType | None = None,  # noqa: A002 - the query parameter is called `type`
    category_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(description="Title contains")] = None,
) -> ProductsAdminSummary:
    """All products including drafts and archived ones, newest first."""
    data, count = service.list_products_admin(
        session,
        skip=skip,
        limit=limit,
        status=status,
        type_=type,
        category_id=category_id,
        query=q,
    )
    return ProductsAdminSummary(data=data, count=count)


@router.post("/products", response_model=ProductAdmin)
def admin_create_product(session: SessionDep, data: ProductCreate) -> ProductAdmin:
    product = service.create_product(session, data)
    return service.to_product_admin(session, product)


@router.get("/products/{product_id}", response_model=ProductAdmin)
def admin_read_product(session: SessionDep, product_id: uuid.UUID) -> ProductAdmin:
    return service.to_product_admin(session, service.get_product(session, product_id))


@router.patch("/products/{product_id}", response_model=ProductAdmin)
def admin_update_product(
    session: SessionDep, product_id: uuid.UUID, data: ProductUpdate
) -> ProductAdmin:
    product = service.update_product(
        session, service.get_product(session, product_id), data
    )
    return service.to_product_admin(session, product)


@router.delete("/products/{product_id}", response_model=Message)
def admin_delete_product(
    session: SessionDep, storage: StorageDep, product_id: uuid.UUID
) -> Message:
    """Delete a draft or archived product with its variants, prices and slots."""
    service.delete_product(session, storage, service.get_product(session, product_id))
    return Message(message="Product deleted successfully")


@router.post("/products/{product_id}/publish", response_model=ProductAdmin)
def admin_publish_product(session: SessionDep, product_id: uuid.UUID) -> ProductAdmin:
    """422 unless there is an active variant and every active variant has a price,
    a file (digital) or a stock quantity (physical)."""
    product = service.publish_product(session, service.get_product(session, product_id))
    return service.to_product_admin(session, product)


@router.post("/products/{product_id}/unpublish", response_model=ProductAdmin)
def admin_unpublish_product(session: SessionDep, product_id: uuid.UUID) -> ProductAdmin:
    product = service.unpublish_product(
        session, service.get_product(session, product_id)
    )
    return service.to_product_admin(session, product)


@router.post("/products/{product_id}/archive", response_model=ProductAdmin)
def admin_archive_product(session: SessionDep, product_id: uuid.UUID) -> ProductAdmin:
    product = service.archive_product(session, service.get_product(session, product_id))
    return service.to_product_admin(session, product)


# --- options ---


@router.post("/products/{product_id}/options", response_model=OptionPublic)
def admin_create_option(
    session: SessionDep, product_id: uuid.UUID, data: OptionCreate
) -> OptionPublic:
    product = service.get_product(session, product_id)
    return service.to_option_public(service.create_option(session, product, data))


@router.patch("/options/{option_id}", response_model=OptionPublic)
def admin_update_option(
    session: SessionDep, option_id: uuid.UUID, data: OptionUpdate
) -> OptionPublic:
    option = service.get_option(session, option_id)
    return service.to_option_public(service.update_option(session, option, data))


@router.delete("/options/{option_id}", response_model=Message)
def admin_delete_option(session: SessionDep, option_id: uuid.UUID) -> Message:
    service.delete_option(session, service.get_option(session, option_id))
    return Message(message="Option deleted successfully")


# --- variants and prices ---


@router.post("/products/{product_id}/variants", response_model=VariantAdmin)
def admin_create_variant(
    session: SessionDep, product_id: uuid.UUID, data: VariantCreate
) -> VariantAdmin:
    product = service.get_product(session, product_id)
    variant = service.create_variant(session, product, data)
    return service.to_variant_admin(session, variant)


@router.patch("/variants/{variant_id}", response_model=VariantAdmin)
def admin_update_variant(
    session: SessionDep,
    storage: StorageDep,
    variant_id: uuid.UUID,
    data: VariantUpdate,
) -> VariantAdmin:
    variant = service.get_variant(session, variant_id)
    product = service.get_product(session, variant.product_id)
    updated = service.update_variant(session, storage, product, variant, data)
    return service.to_variant_admin(session, updated)


@router.delete("/variants/{variant_id}", response_model=Message)
def admin_delete_variant(
    session: SessionDep, storage: StorageDep, variant_id: uuid.UUID
) -> Message:
    variant = service.get_variant(session, variant_id)
    product = service.get_product(session, variant.product_id)
    service.delete_variant(session, storage, product, variant)
    return Message(message="Variant deleted successfully")


@router.put("/variants/{variant_id}/prices/{currency}", response_model=PriceAdmin)
def admin_set_price(
    session: SessionDep, variant_id: uuid.UUID, currency: str, data: PriceSet
) -> PriceAdmin:
    """Create or replace the price in one currency (422 for a currency not in `STORE_CURRENCIES`)."""
    variant = service.get_variant(session, variant_id)
    price = service.set_price(session, variant, currency, data.amount)
    return service.price_admin(price)


@router.delete("/variants/{variant_id}/prices/{currency}", response_model=Message)
def admin_delete_price(
    session: SessionDep, variant_id: uuid.UUID, currency: str
) -> Message:
    variant = service.get_variant(session, variant_id)
    product = service.get_product(session, variant.product_id)
    service.delete_price(session, product, variant, currency)
    return Message(message="Price deleted successfully")


# --- slots ---


@router.get("/products/{product_id}/slots", response_model=SlotsAdmin)
def admin_read_slots(session: SessionDep, product_id: uuid.UUID) -> SlotsAdmin:
    service.get_product(session, product_id)
    slots = service.list_slots(session, product_id)
    return SlotsAdmin(data=[service.to_slot_admin(s) for s in slots], count=len(slots))


@router.post("/products/{product_id}/slots", response_model=SlotAdmin)
def admin_create_slot(
    session: SessionDep, product_id: uuid.UUID, data: SlotCreate
) -> SlotAdmin:
    product = service.get_product(session, product_id)
    return service.to_slot_admin(service.create_slot(session, product, data))


@router.patch("/slots/{slot_id}", response_model=SlotAdmin)
def admin_update_slot(
    session: SessionDep, slot_id: uuid.UUID, data: SlotUpdate
) -> SlotAdmin:
    slot = service.get_slot(session, slot_id)
    return service.to_slot_admin(service.update_slot(session, slot, data))


@router.delete("/slots/{slot_id}", response_model=Message)
def admin_delete_slot(session: SessionDep, slot_id: uuid.UUID) -> Message:
    service.delete_slot(session, service.get_slot(session, slot_id))
    return Message(message="Slot deleted successfully")

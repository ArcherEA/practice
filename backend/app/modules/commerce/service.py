"""Commerce service: catalog rules, publishing checks, queries and response building.

Routes stay thin and call these functions. Errors are `HTTPException`s, as in the
rest of the API: 404 unknown ids, 409 clashes (slug, SKU, combination), 422 for
every validation rule of the task (currency, options, stock, files, slots).
"""

import json
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, func, select

from app.core import richtext
from app.core.config import settings
from app.core.files import check_public_image_files, register_file_guard
from app.core.files import delete_file as delete_stored_file
from app.core.richtext import JsonDict
from app.core.roles import UserRole, has_role
from app.core.slugs import unique_slug
from app.core.storage import Storage
from app.models import File, FileStatus, User, get_datetime_utc
from app.modules.commerce import money
from app.modules.commerce.models import (
    Product,
    ProductCategory,
    ProductOption,
    ProductStatus,
    ProductType,
    ServiceSlot,
    Variant,
    VariantPrice,
)
from app.modules.commerce.schemas import (
    MAX_OPTIONS,
    CurrencyInfo,
    OptionCreate,
    OptionOffer,
    OptionPublic,
    OptionUpdate,
    PriceAdmin,
    ProductAdmin,
    ProductAdminSummary,
    ProductCategoryCreate,
    ProductCategoryPublic,
    ProductCategoryUpdate,
    ProductCreate,
    ProductDetail,
    ProductListItem,
    ProductUpdate,
    SlotAdmin,
    SlotCreate,
    SlotPublic,
    SlotUpdate,
    StoreConfig,
    VariantAdmin,
    VariantCreate,
    VariantFile,
    VariantOffer,
    VariantUpdate,
)


def now() -> datetime:
    """The module clock; tests replace it instead of sleeping."""
    return get_datetime_utc()


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _commit(session: Session) -> None:
    """Commit; a lost race on a unique constraint becomes 409 instead of 500."""
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Conflicting change (slug or SKU already in use)"
        ) from None


# --- store settings and money ---


def store_config() -> StoreConfig:
    return StoreConfig(
        currencies=[
            CurrencyInfo(code=code, exponent=money.exponent(code))
            for code in money.allowed_currencies()
        ],
        default_currency=money.default_currency(),
        timezone=settings.STORE_TIMEZONE,
    )


def require_currency(code: str) -> str:
    """Normalized currency code, or 422 when it is not in STORE_CURRENCIES."""
    normalized = money.normalize_currency(code)
    if not money.is_allowed(normalized):
        raise _unprocessable(
            f"Unknown currency '{code}'. Allowed: {', '.join(money.allowed_currencies())}"
        )
    return normalized


def public_currency(code: str | None) -> str:
    return money.default_currency() if not code else require_currency(code)


# --- file guard: a file used by a variant is never deleted behind its back ---


def _file_in_use(session: Session, file_id: uuid.UUID) -> bool:
    return (
        session.exec(select(Variant.id).where(Variant.file_id == file_id)).first()
        is not None
    )


register_file_guard(_file_in_use)


def release_files(
    session: Session, storage: Storage, file_ids: Sequence[uuid.UUID]
) -> None:
    """Delete product files (row + object) that no variant references any more."""
    for file_id in dict.fromkeys(file_ids):
        file = session.get(File, file_id)
        if file is not None and not _file_in_use(session, file_id):
            delete_stored_file(session=session, storage=storage, file=file)


def check_product_file(session: Session, file_id: uuid.UUID) -> File:
    """A ready, private file uploaded by an admin (never someone else's private file)."""
    file = session.get(File, file_id)
    if file is None:
        raise _unprocessable(f"File {file_id} not found")
    if file.status != FileStatus.ready:
        raise _unprocessable(f"File {file_id} is not confirmed yet")
    if file.public:
        raise _unprocessable("A product file must be private, not public")
    owner = session.get(User, file.owner_id)
    if owner is None or not has_role(owner, UserRole.admin):
        raise _unprocessable(
            "A product file must be uploaded by an admin (use the commerce upload)"
        )
    return file


def get_own_pending_product_file(
    session: Session, user: User, file_id: uuid.UUID
) -> File:
    """The caller's own private file (404 for anyone else's, like the files API)."""
    file = session.get(File, file_id)
    if file is None or file.owner_id != user.id or file.public:
        raise HTTPException(status_code=404, detail="File not found")
    return file


# --- slugs ---

# Product slugs that would collide with the storefront's static pages
# (`/shop/cart`, `/shop/category/<slug>`); treated as taken, so they get a suffix.
RESERVED_PRODUCT_SLUGS = frozenset({"cart", "category"})


def _slug_for(
    session: Session,
    model: type[Product] | type[ProductCategory],
    text: str,
    exclude_id: uuid.UUID | None = None,
) -> str:
    def taken(candidate: str) -> bool:
        if model is Product and candidate in RESERVED_PRODUCT_SLUGS:
            return True
        statement = select(model.id).where(model.slug == candidate)
        if exclude_id is not None:
            statement = statement.where(model.id != exclude_id)
        return session.exec(statement).first() is not None

    return unique_slug(text, taken)


# --- description and images ---


def image_url(file_id: uuid.UUID | str) -> str:
    """Stable, non-expiring URL of a public image (redirects to storage)."""
    return f"{settings.API_V1_STR}/files/{file_id}/content"


def clean_description(session: Session, raw: JsonDict) -> JsonDict:
    try:
        result = richtext.sanitize_body(raw)
    except richtext.BodyValidationError as exc:
        raise _unprocessable(f"Invalid description: {exc}") from None
    check_public_image_files(session, result.image_file_ids)
    return result.body


def _clean_images(session: Session, ids: Sequence[uuid.UUID]) -> list[str]:
    if len(set(ids)) != len(ids):
        raise _unprocessable("image_file_ids contains duplicates")
    check_public_image_files(session, set(ids))
    return [str(file_id) for file_id in ids]


def _live_image_ids(session: Session, products: Sequence[Product]) -> set[str]:
    """Image ids that still exist as ready, public files (a deleted file just disappears)."""
    wanted = {uuid.UUID(i) for p in products for i in p.image_file_ids}
    if not wanted:
        return set()
    rows = session.exec(
        select(File.id).where(
            col(File.id).in_(wanted),
            File.status == FileStatus.ready,
            File.public == True,  # noqa: E712 - SQL comparison
        )
    ).all()
    return {str(row) for row in rows}


def _image_urls(product: Product, live: set[str]) -> list[str]:
    return [image_url(i) for i in product.image_file_ids if i in live]


def public_image_urls(session: Session, product: Product) -> list[str]:
    """Image URLs of one product, in order, skipping files that no longer exist."""
    return _image_urls(product, _live_image_ids(session, [product]))


# --- categories ---


def get_category(session: Session, category_id: uuid.UUID) -> ProductCategory:
    category = session.get(ProductCategory, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


def list_categories(
    session: Session, *, with_published_products: bool = False
) -> Sequence[ProductCategory]:
    statement = select(ProductCategory)
    if with_published_products:
        statement = statement.where(
            col(ProductCategory.id).in_(
                select(Product.category_id).where(
                    Product.status == ProductStatus.published
                )
            )
        )
    return session.exec(
        statement.order_by(col(ProductCategory.position), col(ProductCategory.name))
    ).all()


def create_category(session: Session, data: ProductCategoryCreate) -> ProductCategory:
    category = ProductCategory(
        name=data.name.strip(),
        slug=_slug_for(session, ProductCategory, data.slug or data.name),
        position=data.position,
    )
    session.add(category)
    _commit(session)
    session.refresh(category)
    return category


def update_category(
    session: Session, category: ProductCategory, data: ProductCategoryUpdate
) -> ProductCategory:
    if data.name is not None:
        category.name = data.name.strip()
    if data.slug is not None:
        category.slug = _slug_for(session, ProductCategory, data.slug, category.id)
    if data.position is not None:
        category.position = data.position
    session.add(category)
    _commit(session)
    session.refresh(category)
    return category


def delete_category(session: Session, category: ProductCategory) -> None:
    # Products keep existing: category_id is ON DELETE SET NULL.
    session.delete(category)
    session.commit()


def category_public(category: ProductCategory | None) -> ProductCategoryPublic | None:
    return None if category is None else ProductCategoryPublic.model_validate(category)


def _check_category(session: Session, category_id: uuid.UUID | None) -> None:
    if category_id is not None and session.get(ProductCategory, category_id) is None:
        raise _unprocessable(f"Category {category_id} not found")


# --- products ---


def get_product(session: Session, product_id: uuid.UUID) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


def create_product(session: Session, data: ProductCreate) -> Product:
    _check_category(session, data.category_id)
    product = Product(
        type=data.type,
        title=data.title.strip(),
        slug=_slug_for(session, Product, data.slug or data.title),
        description=clean_description(session, data.description),
        category_id=data.category_id,
        image_file_ids=_clean_images(session, data.image_file_ids),
        seo_title=data.seo_title,
        seo_description=data.seo_description,
    )
    session.add(product)
    _commit(session)
    session.refresh(product)
    return product


def update_product(session: Session, product: Product, data: ProductUpdate) -> Product:
    sent = data.model_fields_set
    if "title" in sent and data.title is not None:
        product.title = data.title.strip()
    if "slug" in sent and data.slug is not None:
        product.slug = _slug_for(session, Product, data.slug, product.id)
    if "description" in sent and data.description is not None:
        product.description = clean_description(session, data.description)
    if "category_id" in sent:
        _check_category(session, data.category_id)
        product.category_id = data.category_id
    if "image_file_ids" in sent and data.image_file_ids is not None:
        product.image_file_ids = _clean_images(session, data.image_file_ids)
    if "seo_title" in sent:
        product.seo_title = data.seo_title
    if "seo_description" in sent:
        product.seo_description = data.seo_description
    _touch(session, product)
    return product


def _touch(session: Session, product: Product) -> None:
    product.updated_at = now()
    session.add(product)
    _commit(session)
    session.refresh(product)


def delete_product(session: Session, storage: Storage, product: Product) -> None:
    if product.status == ProductStatus.published:
        raise HTTPException(
            status_code=409,
            detail="Unpublish or archive the product before deleting it",
        )
    file_ids = [
        f
        for f in session.exec(
            select(Variant.file_id).where(Variant.product_id == product.id)
        ).all()
        if f is not None
    ]
    session.delete(product)  # options, variants, prices, slots: ON DELETE CASCADE
    session.commit()
    release_files(session, storage, file_ids)


def _variants_of(session: Session, product_id: uuid.UUID) -> Sequence[Variant]:
    return session.exec(
        select(Variant)
        .where(Variant.product_id == product_id)
        .order_by(col(Variant.position), col(Variant.sku))
    ).all()


def _options_of(session: Session, product_id: uuid.UUID) -> Sequence[ProductOption]:
    return session.exec(
        select(ProductOption)
        .where(ProductOption.product_id == product_id)
        .order_by(col(ProductOption.position), col(ProductOption.name))
    ).all()


def _prices_by_variant(
    session: Session, variant_ids: Sequence[uuid.UUID], currency: str | None = None
) -> dict[uuid.UUID, list[VariantPrice]]:
    result: dict[uuid.UUID, list[VariantPrice]] = defaultdict(list)
    if not variant_ids:
        return result
    statement = select(VariantPrice).where(
        col(VariantPrice.variant_id).in_(variant_ids)
    )
    if currency is not None:
        statement = statement.where(VariantPrice.currency == currency)
    for price in session.exec(statement.order_by(col(VariantPrice.currency))).all():
        result[price.variant_id].append(price)
    return result


# --- publishing rules ---


def _variant_issues(
    product: Product, variant: Variant, prices: Sequence[VariantPrice]
) -> list[str]:
    """Why an *active* variant cannot be sold (empty list = fine)."""
    issues: list[str] = []
    if not prices:
        issues.append(f"Variant {variant.sku} has no price")
    if product.type == ProductType.digital and variant.file_id is None:
        issues.append(f"Digital variant {variant.sku} has no file")
    if product.type == ProductType.physical and variant.stock is None:
        issues.append(f"Physical variant {variant.sku} needs a stock quantity")
    return issues


def _publish_issues(session: Session, product: Product) -> list[str]:
    variants = [v for v in _variants_of(session, product.id) if v.is_active]
    if not variants:
        return ["The product needs at least one active variant"]
    prices = _prices_by_variant(session, [v.id for v in variants])
    issues: list[str] = []
    for variant in variants:
        issues.extend(_variant_issues(product, variant, prices.get(variant.id, [])))
    return issues


def _fail(issues: list[str]) -> HTTPException:
    return _unprocessable("; ".join(issues))


def publish_product(session: Session, product: Product) -> Product:
    issues = _publish_issues(session, product)
    if issues:
        raise _fail(issues)
    product.status = ProductStatus.published
    if product.published_at is None:
        product.published_at = now()
    _touch(session, product)
    return product


def unpublish_product(session: Session, product: Product) -> Product:
    product.status = ProductStatus.draft
    _touch(session, product)
    return product


def archive_product(session: Session, product: Product) -> Product:
    product.status = ProductStatus.archived
    _touch(session, product)
    return product


def _save_checked(session: Session, product: Product) -> None:
    """Flush pending changes, refuse them if they would break a published product, commit.

    A published product must stay sellable: a rejected change is rolled back whole.
    """
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Conflicting change (slug or SKU already in use)"
        ) from None
    if product.status == ProductStatus.published:
        issues = _publish_issues(session, product)
        if issues:
            session.rollback()
            raise _fail([*issues, "Unpublish the product first to make this change"])
    session.commit()


# --- options ---


def get_option(session: Session, option_id: uuid.UUID) -> ProductOption:
    option = session.get(ProductOption, option_id)
    if option is None:
        raise HTTPException(status_code=404, detail="Option not found")
    return option


def _has_variants(session: Session, product_id: uuid.UUID) -> bool:
    return (
        session.exec(select(Variant.id).where(Variant.product_id == product_id)).first()
        is not None
    )


def create_option(
    session: Session, product: Product, data: OptionCreate
) -> ProductOption:
    options = _options_of(session, product.id)
    if len(options) >= MAX_OPTIONS:
        raise _unprocessable(f"A product can have at most {MAX_OPTIONS} options")
    if any(o.name.lower() == data.name.lower() for o in options):
        raise _unprocessable(f"Option '{data.name}' already exists")
    if _has_variants(session, product.id):
        raise _unprocessable(
            "Delete the product's variants before adding an option "
            "(every variant needs a value for every option)"
        )
    option = ProductOption(
        product_id=product.id,
        name=data.name,
        values=data.values,
        position=max((o.position for o in options), default=-1) + 1,
    )
    session.add(option)
    session.commit()
    session.refresh(option)
    return option


def update_option(
    session: Session, option: ProductOption, data: OptionUpdate
) -> ProductOption:
    variants = _variants_of(session, option.product_id)
    if data.name is not None and data.name != option.name:
        if variants:
            raise _unprocessable(
                "An option cannot be renamed while the product has variants"
            )
        if any(
            o.id != option.id and o.name.lower() == data.name.lower()
            for o in _options_of(session, option.product_id)
        ):
            raise _unprocessable(f"Option '{data.name}' already exists")
        option.name = data.name
    if data.values is not None:
        used = {v.option_values.get(option.name) for v in variants}
        missing = sorted(value for value in used if value not in data.values and value)
        if missing:
            raise _unprocessable(
                f"Values still used by variants cannot be removed: {', '.join(missing)}"
            )
        option.values = data.values
    if data.position is not None:
        option.position = data.position
    session.add(option)
    session.commit()
    session.refresh(option)
    return option


def delete_option(session: Session, option: ProductOption) -> None:
    if _has_variants(session, option.product_id):
        raise _unprocessable("Delete the product's variants before deleting an option")
    session.delete(option)
    session.commit()


# --- variants and prices ---


def get_variant(session: Session, variant_id: uuid.UUID) -> Variant:
    variant = session.get(Variant, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")
    return variant


def options_key(values: dict[str, str]) -> str:
    return json.dumps(values, sort_keys=True, ensure_ascii=False)


def _check_option_values(
    options: Sequence[ProductOption], values: dict[str, str]
) -> dict[str, str]:
    expected = {o.name: o for o in options}
    if set(values) != set(expected):
        wanted = ", ".join(sorted(expected)) or "none (the product has no options)"
        raise _unprocessable(
            f"option_values must have exactly one value for each option: {wanted}"
        )
    for name, value in values.items():
        if value not in expected[name].values:
            raise _unprocessable(
                f"'{value}' is not an allowed value of option '{name}' "
                f"({', '.join(expected[name].values)})"
            )
    return {name: values[name] for name in sorted(values)}


def _check_unique_variant(
    session: Session,
    product_id: uuid.UUID,
    sku: str,
    key: str,
    exclude_id: uuid.UUID | None,
) -> None:
    for column, value, message in (
        (Variant.sku, sku, f"SKU {sku} is already in use"),
        (
            Variant.options_key,
            key,
            "A variant with these option values already exists",
        ),
    ):
        statement = select(Variant.id).where(column == value)
        if column is Variant.options_key:
            statement = statement.where(Variant.product_id == product_id)
        if exclude_id is not None:
            statement = statement.where(Variant.id != exclude_id)
        if session.exec(statement).first() is not None:
            raise HTTPException(status_code=409, detail=message)


def _check_variant_file(
    session: Session, product: Product, file_id: uuid.UUID | None
) -> None:
    if file_id is None:
        return
    if product.type != ProductType.digital:
        raise _unprocessable("Only digital products can have a file")
    check_product_file(session, file_id)


def _clean_prices(prices: dict[str, int]) -> dict[str, int]:
    cleaned: dict[str, int] = {}
    for code, amount in prices.items():
        currency = require_currency(code)
        if currency in cleaned:
            raise _unprocessable(f"Currency '{currency}' is listed twice")
        if not 0 < amount <= 99_999_999:
            raise _unprocessable("Prices must be between 1 and 99999999 minor units")
        cleaned[currency] = amount
    return cleaned


def create_variant(session: Session, product: Product, data: VariantCreate) -> Variant:
    values = _check_option_values(_options_of(session, product.id), data.option_values)
    key = options_key(values)
    _check_unique_variant(session, product.id, data.sku, key, None)
    _check_variant_file(session, product, data.file_id)
    prices = _clean_prices(data.prices)
    position = (
        data.position
        if data.position is not None
        else max((v.position for v in _variants_of(session, product.id)), default=-1)
        + 1
    )
    variant = Variant(
        product_id=product.id,
        sku=data.sku,
        option_values=values,
        options_key=key,
        stock=data.stock,
        file_id=data.file_id,
        is_active=data.is_active,
        position=position,
    )
    session.add(variant)
    for currency, amount in prices.items():
        session.add(
            VariantPrice(variant_id=variant.id, currency=currency, amount=amount)
        )
    _save_checked(session, product)
    session.refresh(variant)
    return variant


def update_variant(
    session: Session,
    storage: Storage,
    product: Product,
    variant: Variant,
    data: VariantUpdate,
) -> Variant:
    sent = data.model_fields_set
    old_file_id = variant.file_id
    new_values = variant.option_values
    if "option_values" in sent and data.option_values is not None:
        new_values = _check_option_values(
            _options_of(session, product.id), data.option_values
        )
    new_sku = data.sku if "sku" in sent and data.sku is not None else variant.sku
    new_key = options_key(new_values)
    # Check before assigning: a query after the change would autoflush it.
    _check_unique_variant(session, product.id, new_sku, new_key, variant.id)
    variant.option_values = new_values
    variant.options_key = new_key
    variant.sku = new_sku
    if "stock" in sent:
        variant.stock = data.stock
    if "file_id" in sent:
        _check_variant_file(session, product, data.file_id)
        variant.file_id = data.file_id
    if "is_active" in sent and data.is_active is not None:
        variant.is_active = data.is_active
    if "position" in sent and data.position is not None:
        variant.position = data.position
    session.add(variant)
    _save_checked(session, product)
    session.refresh(variant)
    if old_file_id is not None and old_file_id != variant.file_id:
        release_files(session, storage, [old_file_id])
    return variant


def delete_variant(
    session: Session, storage: Storage, product: Product, variant: Variant
) -> None:
    file_id = variant.file_id
    session.delete(variant)  # prices: ON DELETE CASCADE
    _save_checked(session, product)
    if file_id is not None:
        release_files(session, storage, [file_id])


def set_price(
    session: Session, variant: Variant, currency: str, amount: int
) -> VariantPrice:
    code = require_currency(currency)
    price = session.get(VariantPrice, (variant.id, code))
    if price is None:
        price = VariantPrice(variant_id=variant.id, currency=code, amount=amount)
    else:
        price.amount = amount
    session.add(price)
    session.commit()
    session.refresh(price)
    return price


def delete_price(
    session: Session, product: Product, variant: Variant, currency: str
) -> None:
    code = money.normalize_currency(currency)
    price = session.get(VariantPrice, (variant.id, code))
    if price is None:
        raise HTTPException(status_code=404, detail="Price not found")
    session.delete(price)
    _save_checked(session, product)


# --- slots ---


def get_slot(session: Session, slot_id: uuid.UUID) -> ServiceSlot:
    slot = session.get(ServiceSlot, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot not found")
    return slot


def list_slots(session: Session, product_id: uuid.UUID) -> Sequence[ServiceSlot]:
    return session.exec(
        select(ServiceSlot)
        .where(ServiceSlot.product_id == product_id)
        .order_by(col(ServiceSlot.starts_at))
    ).all()


def _check_slot_window(
    session: Session,
    product_id: uuid.UUID,
    starts_at: datetime,
    ends_at: datetime,
    exclude_id: uuid.UUID | None,
) -> None:
    if ends_at <= starts_at:
        raise _unprocessable("A slot must end after it starts")
    statement = select(ServiceSlot.id).where(
        ServiceSlot.product_id == product_id,
        ServiceSlot.starts_at == starts_at,
        ServiceSlot.ends_at == ends_at,
    )
    if exclude_id is not None:
        statement = statement.where(ServiceSlot.id != exclude_id)
    if session.exec(statement).first() is not None:
        raise _unprocessable("A slot with the same start and end already exists")


def create_slot(session: Session, product: Product, data: SlotCreate) -> ServiceSlot:
    if product.type != ProductType.service:
        raise _unprocessable("Only service products have slots")
    _check_slot_window(session, product.id, data.starts_at, data.ends_at, None)
    slot = ServiceSlot(
        product_id=product.id,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        capacity=data.capacity,
        is_active=data.is_active,
    )
    session.add(slot)
    _commit(session)
    session.refresh(slot)
    return slot


def update_slot(session: Session, slot: ServiceSlot, data: SlotUpdate) -> ServiceSlot:
    starts_at = data.starts_at or slot.starts_at
    ends_at = data.ends_at or slot.ends_at
    _check_slot_window(session, slot.product_id, starts_at, ends_at, slot.id)
    slot.starts_at = starts_at
    slot.ends_at = ends_at
    if data.capacity is not None:
        slot.capacity = data.capacity
    if data.is_active is not None:
        slot.is_active = data.is_active
    session.add(slot)
    _commit(session)
    session.refresh(slot)
    return slot


def delete_slot(session: Session, slot: ServiceSlot) -> None:
    session.delete(slot)
    session.commit()


def remaining_capacity(slot: ServiceSlot) -> int:
    """Seats left. Sold and held seats are subtracted once checkout exists (task 027)."""
    return slot.capacity


def _upcoming_slots(
    session: Session, product_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[ServiceSlot]]:
    result: dict[uuid.UUID, list[ServiceSlot]] = defaultdict(list)
    if not product_ids:
        return result
    slots = session.exec(
        select(ServiceSlot)
        .where(
            col(ServiceSlot.product_id).in_(product_ids),
            ServiceSlot.is_active == True,  # noqa: E712 - SQL comparison
            ServiceSlot.starts_at > now(),
        )
        .order_by(col(ServiceSlot.starts_at))
    ).all()
    for slot in slots:
        if remaining_capacity(slot) > 0:
            result[slot.product_id].append(slot)
    return result


# --- responses: admin ---


def price_admin(price: VariantPrice) -> PriceAdmin:
    return PriceAdmin(
        currency=price.currency,
        amount=price.amount,
        formatted=money.format_amount(price.amount, price.currency),
    )


def to_variant_admin(session: Session, variant: Variant) -> VariantAdmin:
    return _variants_admin(session, [variant])[0]


def _variants_admin(
    session: Session, variants: Sequence[Variant]
) -> list[VariantAdmin]:
    prices = _prices_by_variant(session, [v.id for v in variants])
    file_ids = {v.file_id for v in variants if v.file_id is not None}
    files: dict[uuid.UUID, File] = {}
    if file_ids:
        files = {
            f.id: f
            for f in session.exec(select(File).where(col(File.id).in_(file_ids)))
        }
    result: list[VariantAdmin] = []
    for variant in variants:
        file = files.get(variant.file_id) if variant.file_id else None
        result.append(
            VariantAdmin(
                id=variant.id,
                product_id=variant.product_id,
                sku=variant.sku,
                option_values=variant.option_values,
                stock=variant.stock,
                file=None
                if file is None
                else VariantFile(
                    id=file.id,
                    filename=file.filename,
                    content_type=file.content_type,
                    size=file.size,
                ),
                is_active=variant.is_active,
                position=variant.position,
                prices=[price_admin(p) for p in prices.get(variant.id, [])],
            )
        )
    return result


def to_option_public(option: ProductOption) -> OptionPublic:
    return OptionPublic.model_validate(option)


def to_slot_admin(slot: ServiceSlot) -> SlotAdmin:
    return SlotAdmin.model_validate(slot)


def to_product_admin(session: Session, product: Product) -> ProductAdmin:
    live = _live_image_ids(session, [product])
    return ProductAdmin(
        id=product.id,
        type=product.type,
        slug=product.slug,
        title=product.title,
        status=product.status,
        description=_resolved_description(product),
        category_id=product.category_id,
        image_file_ids=[uuid.UUID(i) for i in product.image_file_ids],
        image_urls=_image_urls(product, live),
        seo_title=product.seo_title,
        seo_description=product.seo_description,
        created_at=product.created_at,
        updated_at=product.updated_at,
        published_at=product.published_at,
        options=[to_option_public(o) for o in _options_of(session, product.id)],
        variants=_variants_admin(session, _variants_of(session, product.id)),
    )


def _resolved_description(product: Product) -> JsonDict:
    """Description for responses: image nodes get ``attrs.src`` (the stable content URL)."""
    return richtext.with_image_urls(product.description, image_url("{file_id}"))


def list_products_admin(
    session: Session,
    *,
    skip: int,
    limit: int,
    status: ProductStatus | None = None,
    type_: ProductType | None = None,
    category_id: uuid.UUID | None = None,
    query: str | None = None,
) -> tuple[list[ProductAdminSummary], int]:
    statement = select(Product)
    if status is not None:
        statement = statement.where(Product.status == status)
    if type_ is not None:
        statement = statement.where(Product.type == type_)
    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(col(Product.title).ilike(f"%{escaped}%"))
    count = session.exec(select(func.count()).select_from(statement.subquery())).one()
    products = session.exec(
        statement.order_by(col(Product.created_at).desc(), col(Product.id))
        .offset(skip)
        .limit(limit)
    ).all()
    live = _live_image_ids(session, products)
    summaries = []
    for product in products:
        urls = _image_urls(product, live)
        summaries.append(
            ProductAdminSummary(
                id=product.id,
                type=product.type,
                slug=product.slug,
                title=product.title,
                status=product.status,
                category_id=product.category_id,
                image_url=urls[0] if urls else None,
                created_at=product.created_at,
                updated_at=product.updated_at,
                published_at=product.published_at,
            )
        )
    return summaries, count


# --- public catalog ---


def _in_stock(variant: Variant) -> bool:
    return variant.stock is None or variant.stock > 0


def list_products_public(
    session: Session,
    *,
    skip: int,
    limit: int,
    currency: str,
    category_slug: str | None = None,
    type_: ProductType | None = None,
) -> tuple[list[ProductListItem], int]:
    statement = select(Product).where(Product.status == ProductStatus.published)
    if type_ is not None:
        statement = statement.where(Product.type == type_)
    if category_slug:
        statement = statement.where(
            col(Product.category_id).in_(
                select(ProductCategory.id).where(ProductCategory.slug == category_slug)
            )
        )
    count = session.exec(select(func.count()).select_from(statement.subquery())).one()
    products = session.exec(
        statement.order_by(
            col(Product.published_at).desc(),
            col(Product.created_at).desc(),
            col(Product.id),
        )
        .offset(skip)
        .limit(limit)
    ).all()
    ids = [p.id for p in products]
    variants_by_product: dict[uuid.UUID, list[Variant]] = defaultdict(list)
    if ids:
        for variant in session.exec(
            select(Variant).where(
                col(Variant.product_id).in_(ids),
                Variant.is_active == True,  # noqa: E712 - SQL comparison
            )
        ):
            variants_by_product[variant.product_id].append(variant)
    prices = _prices_by_variant(
        session, [v.id for vs in variants_by_product.values() for v in vs], currency
    )
    service_ids = [p.id for p in products if p.type == ProductType.service]
    slots = _upcoming_slots(session, service_ids)
    categories = {
        c.id: c
        for c in session.exec(
            select(ProductCategory).where(
                col(ProductCategory.id).in_(
                    [p.category_id for p in products if p.category_id is not None]
                )
            )
        )
    }
    live = _live_image_ids(session, products)
    items: list[ProductListItem] = []
    for product in products:
        sellable = [
            v
            for v in variants_by_product.get(product.id, [])
            if prices.get(v.id) and _in_stock(v)
        ]
        if product.type == ProductType.service and not slots.get(product.id):
            sellable = []
        amounts = [
            prices[v.id][0].amount for v in sellable
        ]  # one row per variant: the requested currency
        urls = _image_urls(product, live)
        items.append(
            ProductListItem(
                id=product.id,
                slug=product.slug,
                title=product.title,
                type=product.type,
                category=category_public(categories.get(product.category_id))
                if product.category_id
                else None,
                image_url=urls[0] if urls else None,
                currency=currency,
                from_price=min(amounts) if amounts else None,
                available=bool(sellable),
            )
        )
    return items, count


def get_published_product(session: Session, slug: str) -> Product:
    product = session.exec(
        select(Product).where(
            Product.slug == slug, Product.status == ProductStatus.published
        )
    ).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


def to_product_detail(
    session: Session, product: Product, currency: str
) -> ProductDetail:
    variants = [v for v in _variants_of(session, product.id) if v.is_active]
    prices = _prices_by_variant(session, [v.id for v in variants], currency)
    slots = _upcoming_slots(session, [product.id]).get(product.id, [])
    has_slots = product.type != ProductType.service or bool(slots)
    offers: list[VariantOffer] = []
    for variant in variants:
        row = prices.get(variant.id, [])
        in_stock = _in_stock(variant) and has_slots
        offers.append(
            VariantOffer(
                id=variant.id,
                sku=variant.sku,
                option_values=variant.option_values,
                currency=currency,
                price=row[0].amount if row else None,
                available=bool(row) and in_stock,
                in_stock=in_stock,
                stock=variant.stock if product.type == ProductType.physical else None,
            )
        )
    live = _live_image_ids(session, [product])
    category = (
        session.get(ProductCategory, product.category_id)
        if product.category_id
        else None
    )
    return ProductDetail(
        id=product.id,
        slug=product.slug,
        title=product.title,
        type=product.type,
        description=_resolved_description(product),
        category=category_public(category),
        image_urls=_image_urls(product, live),
        seo_title=product.seo_title,
        seo_description=product.seo_description,
        published_at=product.published_at,
        currency=currency,
        options=[
            OptionOffer(name=o.name, values=o.values)
            for o in _options_of(session, product.id)
        ],
        variants=offers,
        slots=[
            SlotPublic(
                id=s.id,
                starts_at=s.starts_at,
                ends_at=s.ends_at,
                capacity=s.capacity,
                remaining=remaining_capacity(s),
            )
            for s in slots
        ],
        store_timezone=settings.STORE_TIMEZONE,
    )


def public_categories(session: Session) -> list[ProductCategoryPublic]:
    return [
        ProductCategoryPublic.model_validate(c)
        for c in list_categories(session, with_published_products=True)
    ]

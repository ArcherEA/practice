"""Request and response schemas of the commerce module."""

import re
import uuid
from datetime import UTC, datetime

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.core.richtext import JsonDict, empty_body
from app.modules.commerce.models import ProductStatus, ProductType

# Stripe's upper limit for one amount in minor units (8 digits).
MAX_AMOUNT = 99_999_999
MAX_OPTIONS = 3
MAX_OPTION_VALUES = 30
MAX_IMAGES = 10
SKU_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9._-]*")


def _unique_clean(values: list[str], what: str) -> list[str]:
    cleaned = [value.strip() for value in values]
    if any(not value or len(value) > 50 for value in cleaned):
        raise ValueError(f"each {what} must be 1-50 characters")
    if len({value.lower() for value in cleaned}) != len(cleaned):
        raise ValueError(f"{what}s must be unique")
    return cleaned


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("must include a timezone, for example 2026-12-01T10:00:00Z")
    return value.astimezone(UTC)


# --- store settings ---


class CurrencyInfo(SQLModel):
    code: str
    exponent: int = Field(description="Digits after the decimal point (jpy 0, usd 2)")


class StoreConfig(SQLModel):
    currencies: list[CurrencyInfo]
    default_currency: str
    timezone: str


# --- categories ---


class ProductCategoryCreate(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="Optional; generated from the name when omitted",
    )
    position: int = Field(default=0, ge=0, le=100_000)


class ProductCategoryUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    position: int | None = Field(default=None, ge=0, le=100_000)


class ProductCategoryPublic(SQLModel):
    id: uuid.UUID
    name: str
    slug: str
    position: int


class ProductCategoriesPublic(SQLModel):
    data: list[ProductCategoryPublic]
    count: int


# --- options ---


class OptionCreate(SQLModel):
    name: str = Field(min_length=1, max_length=50)
    values: list[str] = Field(min_length=1, max_length=MAX_OPTION_VALUES)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value

    @field_validator("values")
    @classmethod
    def _values(cls, values: list[str]) -> list[str]:
        return _unique_clean(values, "value")


class OptionUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    values: list[str] | None = Field(
        default=None, min_length=1, max_length=MAX_OPTION_VALUES
    )
    position: int | None = Field(default=None, ge=0, le=100)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value

    @field_validator("values")
    @classmethod
    def _values(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else _unique_clean(values, "value")


class OptionPublic(SQLModel):
    id: uuid.UUID
    name: str
    position: int
    values: list[str]


# --- variants and prices ---


class PriceSet(SQLModel):
    amount: int = Field(
        gt=0, le=MAX_AMOUNT, description="Integer minor units (cents; yen for jpy)"
    )


class PriceAdmin(SQLModel):
    currency: str
    amount: int
    formatted: str


def _check_sku(value: str) -> str:
    value = value.strip().upper()
    if not SKU_PATTERN.fullmatch(value):
        raise ValueError("sku may contain letters, digits, '.', '_' and '-'")
    return value


class VariantCreate(SQLModel):
    sku: str = Field(min_length=1, max_length=64)
    option_values: dict[str, str] = Field(
        default_factory=dict,
        description='One value per product option, e.g. {"Size": "M"}',
    )
    stock: int | None = Field(
        default=None,
        ge=0,
        description="Physical: units in stock (required to publish). Empty = unlimited",
    )
    file_id: uuid.UUID | None = Field(
        default=None, description="Digital products: the private file to deliver"
    )
    is_active: bool = True
    position: int | None = Field(default=None, ge=0, le=10_000)
    prices: dict[str, int] = Field(
        default_factory=dict,
        description="Optional prices by currency code, in minor units",
    )

    @field_validator("sku")
    @classmethod
    def _sku(cls, value: str) -> str:
        return _check_sku(value)


class VariantUpdate(SQLModel):
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    option_values: dict[str, str] | None = None
    stock: int | None = Field(default=None, ge=0)
    file_id: uuid.UUID | None = None
    is_active: bool | None = None
    position: int | None = Field(default=None, ge=0, le=10_000)

    @field_validator("sku")
    @classmethod
    def _sku(cls, value: str | None) -> str | None:
        return None if value is None else _check_sku(value)


class VariantFile(SQLModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size: int


class VariantAdmin(SQLModel):
    id: uuid.UUID
    product_id: uuid.UUID
    sku: str
    option_values: dict[str, str]
    stock: int | None
    file: VariantFile | None
    is_active: bool
    position: int
    prices: list[PriceAdmin]


# --- slots ---


class SlotCreate(SQLModel):
    starts_at: datetime
    ends_at: datetime
    capacity: int = Field(ge=1, le=100_000)
    is_active: bool = True

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _aware_utc(value)


class SlotUpdate(SQLModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    capacity: int | None = Field(default=None, ge=1, le=100_000)
    is_active: bool | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware_utc(value)


class SlotAdmin(SQLModel):
    id: uuid.UUID
    product_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    capacity: int
    is_active: bool


class SlotsAdmin(SQLModel):
    data: list[SlotAdmin]
    count: int


# --- products (admin) ---


class ProductCreate(SQLModel):
    type: ProductType
    title: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="Optional; generated from the title when omitted",
    )
    description: JsonDict = Field(
        default_factory=empty_body,
        description="Tiptap JSON document (same allow-list as posts)",
    )
    category_id: uuid.UUID | None = None
    image_file_ids: list[uuid.UUID] = Field(
        default_factory=list,
        max_length=MAX_IMAGES,
        description="Ordered ready, public image files; the first is the main image",
    )
    seo_title: str | None = Field(default=None, max_length=255)
    seo_description: str | None = Field(default=None, max_length=500)


class ProductUpdate(SQLModel):
    """Send only what changes; send `null` to clear category / SEO fields. The type is fixed."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    description: JsonDict | None = None
    category_id: uuid.UUID | None = None
    image_file_ids: list[uuid.UUID] | None = Field(default=None, max_length=MAX_IMAGES)
    seo_title: str | None = Field(default=None, max_length=255)
    seo_description: str | None = Field(default=None, max_length=500)


class ProductAdminSummary(SQLModel):
    id: uuid.UUID
    type: ProductType
    slug: str
    title: str
    status: ProductStatus
    category_id: uuid.UUID | None
    image_url: str | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class ProductsAdminSummary(SQLModel):
    data: list[ProductAdminSummary]
    count: int


class ProductAdmin(SQLModel):
    id: uuid.UUID
    type: ProductType
    slug: str
    title: str
    status: ProductStatus
    description: JsonDict
    category_id: uuid.UUID | None
    image_file_ids: list[uuid.UUID]
    image_urls: list[str]
    seo_title: str | None
    seo_description: str | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    options: list[OptionPublic]
    variants: list[VariantAdmin]


# --- public catalog ---


class ProductListItem(SQLModel):
    id: uuid.UUID
    slug: str
    title: str
    type: ProductType
    category: ProductCategoryPublic | None
    image_url: str | None
    currency: str
    from_price: int | None = Field(
        description="Lowest price of the sellable variants in `currency` (minor units)"
    )
    available: bool


class ProductsPublic(SQLModel):
    data: list[ProductListItem]
    count: int


class OptionOffer(SQLModel):
    name: str
    values: list[str]


class VariantOffer(SQLModel):
    id: uuid.UUID
    sku: str
    option_values: dict[str, str]
    currency: str
    price: int | None = Field(description="None when there is no price in `currency`")
    available: bool = Field(description="Has a price in `currency` and is in stock")
    in_stock: bool
    stock: int | None = Field(description="Units left (physical products only)")


class SlotPublic(SQLModel):
    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    capacity: int
    remaining: int


class ProductDetail(SQLModel):
    id: uuid.UUID
    slug: str
    title: str
    type: ProductType
    description: JsonDict
    category: ProductCategoryPublic | None
    image_urls: list[str]
    seo_title: str | None
    seo_description: str | None
    published_at: datetime | None
    currency: str
    options: list[OptionOffer]
    variants: list[VariantOffer]
    slots: list[SlotPublic]
    store_timezone: str

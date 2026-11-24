"""Database tables of the commerce module (they always exist, even if the module is off).

Money is stored as **integer minor units** (cents; whole yen for zero-decimal
currencies), never as floats. Enums are plain VARCHAR columns, like `User.role`.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models import get_datetime_utc


class ProductType(StrEnum):
    digital = "digital"
    physical = "physical"
    service = "service"


class ProductStatus(StrEnum):
    draft = "draft"
    published = "published"
    archived = "archived"


class ProductCategory(SQLModel, table=True):
    __tablename__ = "product_category"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(unique=True, index=True, max_length=80)
    position: int = Field(default=0, sa_column_kwargs={"server_default": "0"})


class Product(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    type: ProductType = Field(sa_type=String(20), nullable=False, index=True)
    slug: str = Field(unique=True, index=True, max_length=80)
    title: str = Field(max_length=255)
    # Tiptap JSON, validated by `app.core.richtext.sanitize_body` before it is stored.
    description: dict[str, object] = Field(sa_type=JSONB, nullable=False)
    status: ProductStatus = Field(
        default=ProductStatus.draft,
        sa_type=String(20),
        sa_column_kwargs={"nullable": False, "server_default": "draft"},
        index=True,
    )
    category_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="product_category.id",
        ondelete="SET NULL",
        index=True,
    )
    # Ordered ids (strings) of **public** image files; the first one is the main image.
    image_file_ids: list[str] = Field(
        default_factory=list,
        sa_type=JSONB,
        sa_column_kwargs={"nullable": False, "server_default": "[]"},
    )
    seo_title: str | None = Field(default=None, max_length=255)
    seo_description: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc, sa_type=DateTime(timezone=True)
    )
    published_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class ProductOption(SQLModel, table=True):
    """An option such as "Size" with its allowed values (at most 3 options per product)."""

    __tablename__ = "product_option"
    __table_args__ = (UniqueConstraint("product_id", "name", name="uq_option_name"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    product_id: uuid.UUID = Field(
        foreign_key="product.id", ondelete="CASCADE", index=True
    )
    name: str = Field(min_length=1, max_length=50)
    position: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    values: list[str] = Field(
        default_factory=list,
        sa_type=JSONB,
        sa_column_kwargs={"nullable": False, "server_default": "[]"},
    )


class Variant(SQLModel, table=True):
    __tablename__ = "product_variant"
    __table_args__ = (
        UniqueConstraint("product_id", "options_key", name="uq_variant_options"),
        CheckConstraint("stock IS NULL OR stock >= 0", name="ck_variant_stock"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    product_id: uuid.UUID = Field(
        foreign_key="product.id", ondelete="CASCADE", index=True
    )
    sku: str = Field(unique=True, index=True, max_length=64)
    # {"Size": "M"}; keys = the product's option names (empty for a product without options).
    option_values: dict[str, str] = Field(
        default_factory=dict,
        sa_type=JSONB,
        sa_column_kwargs={"nullable": False, "server_default": "{}"},
    )
    # Canonical form of `option_values`, so the combination is unique per product.
    options_key: str = Field(max_length=500)
    # Physical: units left. None = unlimited (the default for digital and service).
    stock: int | None = Field(default=None)
    # Digital only: the PRIVATE file delivered after payment. RESTRICT: a file in use
    # cannot be removed by deleting its owner or the file itself.
    file_id: uuid.UUID | None = Field(
        default=None, foreign_key="file.id", ondelete="RESTRICT", index=True
    )
    is_active: bool = Field(
        default=True, sa_column_kwargs={"nullable": False, "server_default": "true"}
    )
    position: int = Field(default=0, sa_column_kwargs={"server_default": "0"})


class VariantPrice(SQLModel, table=True):
    __tablename__ = "variant_price"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_variant_price_amount"),)

    variant_id: uuid.UUID = Field(
        foreign_key="product_variant.id", primary_key=True, ondelete="CASCADE"
    )
    currency: str = Field(primary_key=True, max_length=3)
    amount: int = Field(sa_type=BigInteger)


class ServiceSlot(SQLModel, table=True):
    """A fixed bookable time window of a service product (stored in UTC)."""

    __tablename__ = "service_slot"
    __table_args__ = (
        UniqueConstraint("product_id", "starts_at", "ends_at", name="uq_slot_window"),
        CheckConstraint("ends_at > starts_at", name="ck_slot_window"),
        CheckConstraint("capacity >= 1", name="ck_slot_capacity"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    product_id: uuid.UUID = Field(
        foreign_key="product.id", ondelete="CASCADE", index=True
    )
    starts_at: datetime = Field(sa_type=DateTime(timezone=True), index=True)
    ends_at: datetime = Field(sa_type=DateTime(timezone=True))
    capacity: int
    is_active: bool = Field(
        default=True, sa_column_kwargs={"nullable": False, "server_default": "true"}
    )

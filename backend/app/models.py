import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import EmailStr, field_validator
from sqlalchemy import BigInteger, Column, ForeignKey, String, Uuid
from sqlmodel import Field, Relationship, SQLModel

from app.core.roles import UserRole, UserRoleType

if TYPE_CHECKING:
    from app.modules.items.models import Item


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    # Plain VARCHAR (not a Postgres ENUM) so adding roles needs no enum migration.
    role: UserRole = Field(
        default=UserRole.member,
        sa_type=UserRoleType,
        sa_column_kwargs={"nullable": False, "server_default": UserRole.member.value},
    )
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(SQLModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_superuser: bool | None = None
    role: UserRole | None = None
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
    # use_alter: user and file reference each other; this FK is created after both tables.
    avatar_file_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid,
            ForeignKey(
                "file.id",
                ondelete="SET NULL",
                use_alter=True,
                name="fk_user_avatar_file_id_file",
            ),
            nullable=True,
        ),
    )
    items: list["Item"] = Relationship(  # noqa: UP037
        back_populates="owner", cascade_delete=True
    )


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None
    # Public URL, or a short-lived presigned URL; None when there is no avatar.
    avatar_url: str | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


class AvatarSet(SQLModel):
    file_id: uuid.UUID


class FileStatus(StrEnum):
    pending = "pending"
    ready = "ready"


# A bare "type/subtype" media type (no parameters), per RFC 6838 token rules.
_MIME_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}$"
)


class FileCreate(SQLModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=255)
    size: int = Field(gt=0, description="Size in bytes of the file to be uploaded")
    public: bool = False

    @field_validator("filename")
    @classmethod
    def _filename_clean(cls, value: str) -> str:
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise ValueError("Filename must not contain control characters")
        return value

    @field_validator("content_type")
    @classmethod
    def _content_type_is_mime(cls, value: str) -> str:
        if not _MIME_RE.match(value):
            raise ValueError("content_type must look like 'type/subtype'")
        return value


class File(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    key: str = Field(unique=True, max_length=512)
    filename: str = Field(max_length=255)
    content_type: str = Field(max_length=255)
    size: int = Field(sa_type=BigInteger)
    public: bool = False
    status: FileStatus = Field(
        default=FileStatus.pending,
        sa_type=String(20),  # plain VARCHAR, no Postgres ENUM (same as User.role)
        sa_column_kwargs={"nullable": False, "server_default": "pending"},
    )
    created_at: datetime = Field(default_factory=get_datetime_utc, index=True)


class FilePublic(SQLModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    filename: str
    content_type: str
    size: int
    public: bool
    status: FileStatus
    created_at: datetime


class FilesPublic(SQLModel):
    data: list[FilePublic]
    count: int


class UploadTicket(SQLModel):
    """Result of "create upload": PUT the bytes to `upload_url` with `upload_headers`, then confirm."""

    file: FilePublic
    upload_url: str
    upload_method: str = "PUT"
    upload_headers: dict[str, str]
    expires_in: int


class DownloadUrl(SQLModel):
    url: str
    expires_in: int


class UserUsage(SQLModel):
    user_id: uuid.UUID
    email: str
    total_bytes: int
    file_count: int


class StorageUsage(SQLModel):
    total_bytes: int
    limit_bytes: int
    file_count: int
    top_users: list[UserUsage]


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# Import every module's models so SQLModel/Alembic see all tables (and the
# User relationships resolve) whether or not the module is enabled.
# Must stay at the bottom: module models import helpers from this file.
import app.modules.content.models  # noqa: E402, F401
import app.modules.items.models  # noqa: E402, F401

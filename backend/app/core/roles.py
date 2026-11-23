"""Role definitions and the single permission-hierarchy check (see docs/ARCHITECTURE.md)."""

from enum import StrEnum
from typing import Protocol

from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UserRole(StrEnum):
    member = "member"
    editor = "editor"
    moderator = "moderator"
    admin = "admin"


# role -> every role it satisfies (itself included). editor and moderator are siblings.
ROLE_INCLUDES: dict[UserRole, frozenset[UserRole]] = {
    UserRole.member: frozenset({UserRole.member}),
    UserRole.editor: frozenset({UserRole.editor, UserRole.member}),
    UserRole.moderator: frozenset({UserRole.moderator, UserRole.member}),
    UserRole.admin: frozenset(UserRole),
}


class UserRoleType(TypeDecorator[UserRole]):
    """Stored as VARCHAR(20) (no Postgres ENUM type); loaded back as `UserRole`."""

    impl = String(20)
    cache_ok = True

    def process_bind_param(
        self, value: UserRole | str | None, dialect: Dialect
    ) -> str | None:
        return None if value is None else UserRole(value).value

    def process_result_value(
        self, value: str | None, dialect: Dialect
    ) -> UserRole | None:
        return None if value is None else UserRole(value)


class HasRole(Protocol):
    @property
    def is_superuser(self) -> bool: ...

    @property
    def role(self) -> UserRole | str: ...


def has_role(user: HasRole, required: UserRole) -> bool:
    """True if the user's role satisfies `required`. Superusers pass every check."""
    if user.is_superuser:
        return True
    try:
        current = UserRole(user.role)
    except ValueError:
        return False
    return required in ROLE_INCLUDES[current]

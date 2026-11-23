import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.core.roles import UserRole, has_role
from app.models import User

M, E, MOD, A = UserRole.member, UserRole.editor, UserRole.moderator, UserRole.admin

# (user role, required role, expected)
HIERARCHY = [
    (M, M, True),
    (M, E, False),
    (M, MOD, False),
    (M, A, False),
    (E, M, True),
    (E, E, True),
    (E, MOD, False),
    (E, A, False),
    (MOD, M, True),
    (MOD, MOD, True),
    (MOD, E, False),
    (MOD, A, False),
    (A, M, True),
    (A, E, True),
    (A, MOD, True),
    (A, A, True),
]


@pytest.mark.parametrize(("role", "required", "expected"), HIERARCHY)
def test_has_role_hierarchy(role: UserRole, required: UserRole, expected: bool) -> None:
    user = SimpleNamespace(is_superuser=False, role=role)
    assert has_role(user, required) is expected


@pytest.mark.parametrize("role", list(UserRole))
@pytest.mark.parametrize("required", list(UserRole))
def test_superuser_passes_every_check(role: UserRole, required: UserRole) -> None:
    assert has_role(SimpleNamespace(is_superuser=True, role=role), required)


def test_has_role_accepts_plain_string_from_db() -> None:
    assert has_role(SimpleNamespace(is_superuser=False, role="editor"), M)
    assert not has_role(SimpleNamespace(is_superuser=False, role="editor"), A)


def test_has_role_unknown_role_has_no_access() -> None:
    assert not has_role(SimpleNamespace(is_superuser=False, role="bogus"), M)


def test_init_db_superuser_is_admin(db: Session) -> None:
    user = db.exec(select(User).where(User.email == settings.FIRST_SUPERUSER)).one()
    db.refresh(user)
    assert user.is_superuser
    assert user.role == UserRole.admin


def _load_migration() -> ModuleType:
    versions = Path(__file__).resolve().parents[1] / "app" / "alembic" / "versions"
    path = next(versions.glob("637aa9046e9f_*.py"))
    spec = importlib.util.spec_from_file_location("migration_user_role", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_backfills_superusers_and_downgrades() -> None:
    """Run the real migration on a pre-role `user` table in a throwaway schema."""
    migration = _load_migration()
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("CREATE SCHEMA mig_roles_test"))
            conn.execute(text("SET LOCAL search_path TO mig_roles_test"))
            conn.execute(
                text('CREATE TABLE "user" (email text primary key, is_superuser bool)')
            )
            conn.execute(
                text(
                    'INSERT INTO "user" VALUES '
                    "('boss@x.com', true), ('joe@x.com', false)"
                )
            )
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
                rows = dict(conn.execute(text('SELECT email, role FROM "user"')).all())
                assert rows == {"boss@x.com": "admin", "joe@x.com": "member"}
                migration.downgrade()
                columns = (
                    conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = 'mig_roles_test' "
                            "AND table_name = 'user'"
                        )
                    )
                    .scalars()
                    .all()
                )
                assert "role" not in columns
        finally:
            trans.rollback()

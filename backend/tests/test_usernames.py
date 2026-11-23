"""Username rules and the backfill, as pure functions (no database)."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from app.core.usernames import (
    RESERVED_USERNAMES,
    USERNAME_MAX,
    USERNAME_RE,
    backfill_usernames,
    base_username,
    candidates,
    normalize_username,
)

MIGRATION = (
    Path(__file__).parent.parent
    / "app"
    / "alembic"
    / "versions"
    / "bddc69df7d01_add_usernames_bio_follows_and_.py"
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("username_migration", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_lowercases_and_trims() -> None:
    assert normalize_username("  Ada_Lovelace1 ") == "ada_lovelace1"


@pytest.mark.parametrize(
    "value",
    ["ab", "a" * 31, "has space", "dash-ed", "dot.ted", "ünïcode", "", "___"],
)
def test_normalize_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_username(value)


def test_normalize_accepts_the_length_limits() -> None:
    assert normalize_username("abc") == "abc"
    assert normalize_username("a" * 30) == "a" * 30


def test_every_reserved_name_is_rejected_in_any_case() -> None:
    assert {"admin", "api", "me", "null", "undefined", "u", "p"} <= RESERVED_USERNAMES
    for name in RESERVED_USERNAMES:
        # one or two letter names fail on length first; both are rejections
        with pytest.raises(ValueError):
            normalize_username(name.upper())


ID = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"


def test_base_username_prefers_the_name_then_a_member_id() -> None:
    assert base_username("Ada Lovelace", ID) == "ada_lovelace"
    assert base_username("  --Ada!!  Lovelace--  ", ID) == "ada_lovelace"
    # no usable name -> member_<first 8 hex of the id>, never anything from the email
    assert base_username(None, ID) == "member_0f1e2d3c"
    assert base_username("张伟", ID) == "member_0f1e2d3c"
    assert base_username("", ID) == "member_0f1e2d3c"


def test_base_username_pads_and_truncates() -> None:
    assert base_username("ab", ID) == "ab0"
    assert len(base_username("x" * 80, ID)) == USERNAME_MAX


def test_candidates_stay_within_the_limit() -> None:
    gen = candidates("a" * 30)
    names = [next(gen) for _ in range(12)]
    assert names[0] == "a" * 30
    assert names[1] == "a" * 28 + "_2"
    assert all(USERNAME_RE.fullmatch(n) for n in names)
    assert len(set(names)) == 12


def test_backfill_handles_clashes_and_reserved_names() -> None:
    rows: list[tuple[str, str | None]] = [
        ("1", "Ada"),
        ("2", "Ada"),
        ("3", "Ada"),
        ("4", "Admin"),  # reserved
        ("5", "Admin"),  # reserved, and admin_2 is taken
        ("6", "q"),  # too short
        ("7", "Ada 2"),  # clashes with a generated suffix
        ("abcdef12-0000-0000-0000-000000000000", None),  # no name -> member_<id>
    ]
    result = backfill_usernames(rows)
    assert result == {
        "1": "ada",
        "2": "ada_2",
        "3": "ada_3",
        "4": "admin_2",
        "5": "admin_3",
        "6": "q00",
        "7": "ada_2_2",
        "abcdef12-0000-0000-0000-000000000000": "member_abcdef12",
    }
    assert len(set(result.values())) == len(rows)
    assert all(USERNAME_RE.fullmatch(n) for n in result.values())


def test_the_migration_copy_gives_the_same_result_as_the_app_code() -> None:
    rows: list[tuple[str, str | None]] = [
        ("1", "Ada Lovelace"),
        ("2", "ada lovelace"),
        ("3", "Admin"),
        ("4", "x" * 60),
        ("5", "x" * 60),
        ("6abcdef0-1111-2222-3333-444455556666", "张伟"),
        ("7abcdef0-1111-2222-3333-444455556666", None),
        ("8abcdef0-1111-2222-3333-444455556666", ""),
    ]
    migration = load_migration()
    assert migration.backfill_usernames(rows) == backfill_usernames(rows)
    for name in migration.backfill_usernames(rows).values():
        assert USERNAME_RE.fullmatch(name)
        assert name not in migration.RESERVED
    assert migration.RESERVED == RESERVED_USERNAMES

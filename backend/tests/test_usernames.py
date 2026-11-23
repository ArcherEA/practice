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


def test_base_username_prefers_the_name_then_the_email() -> None:
    assert base_username("Ada Lovelace", "x@y.z") == "ada_lovelace"
    assert base_username("  --Ada!!  Lovelace--  ", "x@y.z") == "ada_lovelace"
    assert base_username(None, "John.Smith+tag@example.com") == "john_smith_tag"
    # a name without usable characters falls back to the email
    assert base_username("张伟", "zhang.wei@example.com") == "zhang_wei"
    assert base_username("", "!!@example.com") == "user"


def test_base_username_pads_and_truncates() -> None:
    assert base_username("ab", "x@y.z") == "ab0"
    assert base_username(None, "a@y.z") == "a00"
    assert len(base_username("x" * 80, "a@b.c")) == USERNAME_MAX


def test_candidates_stay_within_the_limit() -> None:
    gen = candidates("a" * 30)
    names = [next(gen) for _ in range(12)]
    assert names[0] == "a" * 30
    assert names[1] == "a" * 28 + "_2"
    assert all(USERNAME_RE.fullmatch(n) for n in names)
    assert len(set(names)) == 12


def test_backfill_handles_clashes_and_reserved_names() -> None:
    rows = [
        ("1", "Ada", "a@x.com"),
        ("2", "Ada", "b@x.com"),
        ("3", "Ada", "c@x.com"),
        ("4", None, "admin@x.com"),  # reserved
        ("5", "Admin", "e@x.com"),  # reserved, and admin_2 is taken
        ("6", None, "q@x.com"),  # too short
        ("7", None, "Ada_2@x.com"),  # clashes with a generated suffix
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
    }
    assert len(set(result.values())) == len(rows)
    assert all(USERNAME_RE.fullmatch(n) for n in result.values())


def test_the_migration_copy_gives_the_same_result_as_the_app_code() -> None:
    rows = [
        ("1", "Ada Lovelace", "a@x.com"),
        ("2", "ada lovelace", "b@x.com"),
        ("3", None, "admin@x.com"),
        ("4", "x" * 60, "c@x.com"),
        ("5", "x" * 60, "d@x.com"),
        ("6", "张伟", "zhang.wei@x.com"),
        ("7", None, "a@x.com"),
        ("8", "", "9@x.com"),
    ]
    migration = load_migration()
    assert migration.backfill_usernames(rows) == backfill_usernames(rows)
    for name in migration.backfill_usernames(rows).values():
        assert USERNAME_RE.fullmatch(name)
        assert name not in migration.RESERVED
    assert migration.RESERVED == RESERVED_USERNAMES

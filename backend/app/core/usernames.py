"""Username rules: lowercase `[a-z0-9_]`, 3-30 characters, reserved words blocked.

Pure functions only (no database), so the rules and the generator are easy to test.
The Alembic migration that added usernames carries its own copy of `slugify` /
`candidates` (migrations must not depend on application code that may change later).
"""

import re
from collections.abc import Callable, Iterator

TakenCheck = Callable[[str], bool]

USERNAME_MIN = 3
USERNAME_MAX = 30
USERNAME_RE = re.compile(r"^[a-z0-9_]{3,30}$")

# Words that would clash with routes or look official. Compared in lowercase.
RESERVED_USERNAMES: frozenset[str] = frozenset(
    {
        "admin",
        "administrator",
        "api",
        "blog",
        "content",
        "community",
        "settings",
        "login",
        "signup",
        "logout",
        "p",
        "u",
        "moderation",
        "notifications",
        "root",
        "support",
        "help",
        "me",
        "null",
        "undefined",
    }
)


def normalize_username(value: str) -> str:
    """Lowercase and validate a username typed by a person; raises `ValueError`."""
    name = value.strip().lower()
    if not USERNAME_RE.fullmatch(name):
        raise ValueError(
            f"Username must be {USERNAME_MIN}-{USERNAME_MAX} characters: "
            "letters, digits and underscores"
        )
    if not name.strip("_"):
        raise ValueError("Username must contain a letter or a digit")
    if name in RESERVED_USERNAMES:
        raise ValueError("This username is reserved")
    return name


def slugify(raw: str) -> str:
    """Lowercase, replace other characters by `_`, collapse and trim `_`; may be empty."""
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]", "_", raw.lower())).strip("_")


def base_username(full_name: str | None, email: str) -> str:
    """A base of 3-30 characters from the full name, else the email local part."""
    base = slugify(full_name or "") or slugify(email.split("@", 1)[0]) or "user"
    base = base[:USERNAME_MAX].rstrip("_")
    return base.ljust(USERNAME_MIN, "0")


def candidates(base: str) -> Iterator[str]:
    """`base`, `base_2`, `base_3`, ... each at most 30 characters (base is shortened)."""
    yield base
    n = 2
    while True:
        suffix = f"_{n}"
        yield f"{base[: USERNAME_MAX - len(suffix)].rstrip('_')}{suffix}"
        n += 1


def pick_username(base: str, is_taken: TakenCheck) -> str:
    """First candidate that is not reserved and not taken."""
    for name in candidates(base):
        if name not in RESERVED_USERNAMES and not is_taken(name):
            return name
    raise AssertionError("unreachable")  # pragma: no cover - candidates never ends


def backfill_usernames(rows: list[tuple[str, str | None, str]]) -> dict[str, str]:
    """Usernames for existing users: `(id, full_name, email)` in order -> `{id: name}`."""
    taken: set[str] = set()
    result: dict[str, str] = {}
    for user_id, full_name, email in rows:
        name = pick_username(base_username(full_name, email), taken.__contains__)
        taken.add(name)
        result[user_id] = name
    return result

"""Slug helpers (pure, no database access)."""

import re
import secrets
import unicodedata
from collections.abc import Callable

MAX_SLUG_LENGTH = 80
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """ASCII-lowercase `text`, non-alphanumerics become single hyphens, max 80 chars.

    Accents are folded (``Café`` -> ``cafe``). Returns ``""`` if nothing is left
    (e.g. a Chinese title); callers then use `random_slug`.
    """
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = _NON_ALNUM.sub("-", folded.lower()).strip("-")
    return slug[:MAX_SLUG_LENGTH].rstrip("-")


def random_slug() -> str:
    """8 random lowercase hex characters."""
    return secrets.token_hex(4)


def base_slug(text: str) -> str:
    """Normalized slug for `text`, or a random one when no ASCII letters/digits remain."""
    return slugify(text) or random_slug()


def unique_slug(text: str, exists: Callable[[str], bool]) -> str:
    """`base_slug(text)`, then ``-2``, ``-3``... until `exists(candidate)` is False.

    The base is shortened where needed so the result never exceeds 80 characters.
    """
    base = base_slug(text)
    candidate = base
    counter = 2
    while exists(candidate):
        suffix = f"-{counter}"
        candidate = f"{base[: MAX_SLUG_LENGTH - len(suffix)].rstrip('-')}{suffix}"
        counter += 1
    return candidate

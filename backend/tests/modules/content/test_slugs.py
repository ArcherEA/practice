import pytest

from app.modules.content.slugs import (
    MAX_SLUG_LENGTH,
    base_slug,
    random_slug,
    slugify,
    unique_slug,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello World", "hello-world"),
        ("  Hello,   World!!  ", "hello-world"),
        ("Rock & Roll -- 101", "rock-roll-101"),
        ("Café déjà vu", "cafe-deja-vu"),
        ("already-a-slug", "already-a-slug"),
        ("UPPER_snake_case", "upper-snake-case"),
        ("Mixed 中文 title", "mixed-title"),
        ("---", ""),
        ("你好，世界", ""),
        ("", ""),
    ],
)
def test_slugify(text: str, expected: str) -> None:
    assert slugify(text) == expected


def test_slugify_truncates_without_trailing_hyphen() -> None:
    slug = slugify("word " * 40)
    assert len(slug) <= MAX_SLUG_LENGTH
    assert not slug.endswith("-")
    assert slugify("a" * 200) == "a" * MAX_SLUG_LENGTH
    # Cut exactly where a hyphen would be the last character.
    assert slugify("a" * 79 + " b") == "a" * 79


def test_random_slug_is_eight_lowercase_chars() -> None:
    values = {random_slug() for _ in range(20)}
    assert len(values) > 1
    for value in values:
        assert len(value) == 8
        assert value == value.lower()
        assert value.isalnum()


def test_base_slug_falls_back_to_random_for_non_ascii() -> None:
    slug = base_slug("你好，世界")
    assert len(slug) == 8
    assert slug.isalnum()
    assert slug.isascii()
    assert base_slug("Hello World") == "hello-world"


def test_unique_slug_appends_counter() -> None:
    taken = {"hello", "hello-2", "hello-3"}
    assert unique_slug("Hello", lambda s: s in taken) == "hello-4"
    assert unique_slug("Other", lambda s: s in taken) == "other"
    assert unique_slug("Hello", lambda s: False) == "hello"


def test_unique_slug_stays_within_max_length() -> None:
    base = "a" * MAX_SLUG_LENGTH
    result = unique_slug("a" * 200, lambda s: s == base)
    assert result.endswith("-2")
    assert len(result) == MAX_SLUG_LENGTH


def test_unique_slug_random_fallback_is_also_made_unique() -> None:
    calls: list[str] = []

    def exists(candidate: str) -> bool:
        calls.append(candidate)
        return len(calls) == 1

    result = unique_slug("你好", exists)
    assert result.endswith("-2")
    assert len(result) == 10

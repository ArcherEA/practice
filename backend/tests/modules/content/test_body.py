import copy
import uuid
from typing import Any

import pytest

from app.modules.content.body import (
    MAX_BODY_BYTES,
    MAX_DEPTH,
    BodyValidationError,
    JsonDict,
    sanitize_body,
    validate_href,
    with_image_urls,
)

FILE_ID = "5c1f6b0e-0d0e-4f64-9a5d-7a8f6a7d2c11"


def doc(*content: JsonDict) -> JsonDict:
    return {"type": "doc", "content": list(content)}


def para(*content: JsonDict) -> JsonDict:
    node: JsonDict = {"type": "paragraph"}
    if content:
        node["content"] = list(content)
    return node


def text(value: str, *marks: JsonDict) -> JsonDict:
    node: JsonDict = {"type": "text", "text": value}
    if marks:
        node["marks"] = list(marks)
    return node


def link(href: object, **extra: object) -> JsonDict:
    return {"type": "link", "attrs": {"href": href, **extra}}


def image(**attrs: object) -> JsonDict:
    return {"type": "image", "attrs": {"fileId": FILE_ID, **attrs}}


def rejects(body: JsonDict, fragment: str) -> None:
    with pytest.raises(BodyValidationError) as exc_info:
        sanitize_body(body)
    assert fragment in str(exc_info.value)


def cleaned(body: JsonDict) -> Any:  # noqa: ANN401 - tests index into the dict tree
    # Any: the cleaned tree is arbitrary JSON; tests navigate it freely.
    return sanitize_body(body).body


FULL_DOC: JsonDict = doc(
    {
        "type": "heading",
        "attrs": {"level": 2},
        "content": [text("Title", {"type": "bold"})],
    },
    para(
        text("plain "),
        text("styled", {"type": "italic"}, {"type": "strike"}, {"type": "code"}),
        {"type": "hardBreak"},
        text("link", link("https://example.com/x", target="_blank", rel="noopener")),
    ),
    {
        "type": "bulletList",
        "content": [{"type": "listItem", "content": [para(text("one"))]}],
    },
    {
        "type": "orderedList",
        "attrs": {"start": 3, "type": None},
        "content": [
            {
                "type": "listItem",
                "content": [
                    para(text("two")),
                    {
                        "type": "bulletList",
                        "content": [{"type": "listItem", "content": [para()]}],
                    },
                ],
            }
        ],
    },
    {"type": "blockquote", "content": [para(text("quote"))]},
    {"type": "codeBlock", "attrs": {"language": "c++"}, "content": [text("print(1)")]},
    {"type": "horizontalRule"},
    image(alt="A cat", title=None),
)


def test_accepts_full_document() -> None:
    result = sanitize_body(FULL_DOC)
    assert result.image_file_ids == {uuid.UUID(FILE_ID)}
    content = result.body["content"]
    assert isinstance(content, list)
    assert [n["type"] for n in content] == [
        "heading",
        "paragraph",
        "bulletList",
        "orderedList",
        "blockquote",
        "codeBlock",
        "horizontalRule",
        "image",
    ]
    # null attributes are dropped, the rest is kept
    assert content[3]["attrs"] == {"start": 3}
    assert content[7]["attrs"] == {"fileId": FILE_ID, "alt": "A cat"}
    # an empty paragraph keeps no empty content array
    inner = content[3]["content"][0]["content"][1]["content"][0]["content"][0]
    assert inner == {"type": "paragraph"}


def test_does_not_mutate_input() -> None:
    original = copy.deepcopy(FULL_DOC)
    sanitize_body(FULL_DOC)
    assert FULL_DOC == original


def test_empty_document_is_valid() -> None:
    assert sanitize_body({"type": "doc"}).body == {"type": "doc", "content": []}
    assert sanitize_body(doc()).body == {"type": "doc", "content": []}


def test_root_must_be_doc() -> None:
    rejects({"type": "paragraph"}, "root node must have type 'doc'")
    rejects({}, "needs a string 'type'")
    rejects({"type": 3}, "needs a string 'type'")


def test_rejects_unknown_node_type() -> None:
    rejects(doc({"type": "script"}), "unknown node type 'script'")
    rejects(doc({"type": "iframe", "attrs": {"src": "x"}}), "unknown node type")
    rejects(doc({"type": "doc"}), "unknown node type 'doc'")


def test_error_reports_path() -> None:
    body = doc(para(text("ok")), para(text("ok"), {"type": "video"}))
    with pytest.raises(BodyValidationError) as exc_info:
        sanitize_body(body)
    assert exc_info.value.path == "body.content[1].content[1]"
    assert "video" in exc_info.value.message


@pytest.mark.parametrize(
    "body",
    [
        doc({"type": "text", "text": "loose"}),
        doc({"type": "listItem"}),
        doc({"type": "hardBreak"}),
        doc({"type": "paragraph", "content": [{"type": "paragraph"}]}),
        doc({"type": "paragraph", "content": [image()]}),
        doc({"type": "bulletList", "content": [{"type": "paragraph"}]}),
        doc({"type": "codeBlock", "content": [{"type": "hardBreak"}]}),
    ],
)
def test_rejects_misplaced_nodes(body: JsonDict) -> None:
    rejects(body, "is not allowed inside")


def test_leaf_nodes_cannot_have_content() -> None:
    rejects(doc({"type": "horizontalRule", "content": [para()]}), "cannot have content")
    node = image()
    node["content"] = [para()]
    rejects(doc(node), "cannot have content")


def test_content_must_be_array_of_objects() -> None:
    rejects({"type": "doc", "content": "x"}, "'content' must be an array")
    rejects({"type": "doc", "content": ["x"]}, "must be an object")


def test_rejects_unknown_node_fields() -> None:
    rejects(doc({"type": "paragraph", "html": "<b>x</b>"}), "unknown field(s): html")
    rejects(doc({"type": "paragraph", "onclick": "x"}), "onclick")


def test_text_rules() -> None:
    rejects(doc(para({"type": "text"})), "non-empty 'text'")
    rejects(doc(para({"type": "text", "text": ""})), "non-empty 'text'")
    rejects(doc(para({"type": "text", "text": 5})), "non-empty 'text'")
    rejects(doc({"type": "paragraph", "text": "x"}), "only text nodes can have 'text'")
    rejects(
        doc(para({"type": "text", "text": "x", "content": []})), "cannot have content"
    )
    rejects(doc(para(text("x" * 100_001))), "too long")


def test_marks_only_on_text_nodes() -> None:
    rejects(doc({"type": "paragraph", "marks": [{"type": "bold"}]}), "only text nodes")
    assert sanitize_body(doc({"type": "paragraph", "marks": []}))  # empty is harmless


def test_rejects_unknown_marks() -> None:
    rejects(
        doc(para(text("x", {"type": "underline"}))), "unknown mark type 'underline'"
    )
    rejects(
        doc(para(text("x", {"type": "textStyle", "attrs": {"color": "red"}}))),
        "unknown mark type",
    )
    rejects(doc(para(text("x", {"attrs": {}}))), "unknown mark type")


def test_marks_structure() -> None:
    rejects(
        doc(para({"type": "text", "text": "x", "marks": "bold"})), "must be an array"
    )
    rejects(
        doc(para({"type": "text", "text": "x", "marks": ["bold"]})),
        "must be an object",
    )
    rejects(
        doc(para(text("x", {"type": "bold", "extra": 1}))), "unknown field(s) on mark"
    )
    rejects(
        doc(para(text("x", {"type": "bold"}, {"type": "bold"}))), "duplicate 'bold'"
    )
    rejects(
        doc(para(text("x", {"type": "bold", "attrs": {"a": 1}}))),
        "does not allow attribute",
    )
    ok = cleaned(doc(para(text("x", {"type": "bold", "attrs": None}))))
    assert ok["content"][0]["content"][0]["marks"] == [{"type": "bold"}]


def test_code_blocks_have_no_marks() -> None:
    rejects(
        doc({"type": "codeBlock", "content": [text("x", {"type": "bold"})]}),
        "code blocks cannot contain marks",
    )


@pytest.mark.parametrize("level", [0, 4, "2", None, True, 1.5])
def test_heading_level_must_be_1_to_3(level: object) -> None:
    rejects(
        doc({"type": "heading", "attrs": {"level": level}, "content": [text("x")]}),
        "heading level must be 1, 2 or 3",
    )


def test_heading_requires_level_attr() -> None:
    rejects(doc({"type": "heading", "content": [text("x")]}), "heading level")


@pytest.mark.parametrize("level", [1, 2, 3])
def test_heading_levels_accepted(level: int) -> None:
    assert sanitize_body(
        doc({"type": "heading", "attrs": {"level": level}, "content": [text("x")]})
    )


def test_node_attrs_must_be_object_and_known() -> None:
    rejects(doc({"type": "paragraph", "attrs": "x"}), "must be an object")
    rejects(
        doc({"type": "paragraph", "attrs": {"style": "color:red"}}),
        "does not allow attribute 'style'",
    )
    rejects(
        doc({"type": "paragraph", "attrs": {"class": "x"}}), "does not allow attribute"
    )
    # null-valued unknown attributes are tolerated and dropped
    result = cleaned(doc({"type": "paragraph", "attrs": {"textAlign": None}}))
    assert result["content"] == [{"type": "paragraph"}]


@pytest.mark.parametrize(
    "attrs",
    [{"start": 0}, {"start": "1"}, {"start": True}, {"type": "x"}, {"start": 1.5}],
)
def test_ordered_list_attrs(attrs: JsonDict) -> None:
    rejects(doc({"type": "orderedList", "attrs": attrs}), "attrs")


def test_ordered_list_valid_attrs() -> None:
    assert sanitize_body(
        doc({"type": "orderedList", "attrs": {"start": 1, "type": "a"}})
    )


@pytest.mark.parametrize("language", ["py thon", "x" * 41, 5, "ünï", "a;b"])
def test_code_block_language_rejected(language: object) -> None:
    rejects(
        doc({"type": "codeBlock", "attrs": {"language": language}}),
        "'language' is not valid",
    )


# --- images ---


def test_image_requires_file_id() -> None:
    rejects(doc({"type": "image"}), "image needs attrs.fileId")
    rejects(doc({"type": "image", "attrs": {"alt": "x"}}), "image needs attrs.fileId")
    rejects(doc({"type": "image", "attrs": {"fileId": 5}}), "image needs attrs.fileId")


def test_image_file_id_must_be_uuid() -> None:
    rejects(doc({"type": "image", "attrs": {"fileId": "nope"}}), "must be a file id")


def test_external_image_url_is_rejected() -> None:
    rejects(
        doc({"type": "image", "attrs": {"src": "https://evil.example/x.png"}}),
        "image needs attrs.fileId",
    )


def test_image_src_from_client_is_stripped() -> None:
    result = cleaned(doc(image(src="https://evil.example/x.png")))
    assert result["content"][0]["attrs"] == {"fileId": FILE_ID}
    assert "evil" not in str(result)


def test_image_unknown_attrs_rejected() -> None:
    rejects(doc(image(onerror="x()")), "does not allow attribute 'onerror'")
    rejects(doc(image(width=100)), "does not allow attribute 'width'")


def test_image_alt_and_title_limits() -> None:
    rejects(doc(image(alt=3)), "'alt'")
    rejects(doc(image(title="x" * 501)), "'title'")


def test_image_file_id_is_normalized_and_collected() -> None:
    result = sanitize_body(doc(image(fileId=FILE_ID.upper()), image()))
    assert result.image_file_ids == {uuid.UUID(FILE_ID)}
    assert result.body["content"][0]["attrs"] == {"fileId": FILE_ID}  # type: ignore[index] # test reads a dict tree


def test_images_allowed_in_quotes_and_list_items() -> None:
    assert sanitize_body(doc({"type": "blockquote", "content": [image()]}))
    assert sanitize_body(
        doc(
            {
                "type": "bulletList",
                "content": [{"type": "listItem", "content": [image()]}],
            }
        )
    )


# --- links ---


@pytest.mark.parametrize(
    "href",
    [
        "https://example.com",
        "http://example.com/a?b=c#d",
        "HTTPS://EXAMPLE.COM",
        "  https://example.com  ",
        "mailto:someone@example.com",
        "MAILTO:someone@example.com",
        "/relative/path",
        "/",
        "/a?b=1#c",
    ],
)
def test_allowed_hrefs(href: str) -> None:
    assert validate_href(href) == href.strip()


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "  javascript:alert(1)",
        "\tjavascript:alert(1)",
        "java\tscript:alert(1)",
        "java\nscript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "DATA:text/html;base64,AAAA",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "ftp://example.com",
        "tel:+123",
        "//evil.example/x",
        "/\\evil.example",
        "relative/path",
        "#anchor",
        "?q=1",
        "example.com",
        "",
        "   ",
        "http://",
        "https:///path",
        "mailto:",
        "mailto:   ",
        "http://exa\x00mple.com",
        "https://example.com/" + "a" * 2048,
    ],
)
def test_rejected_hrefs(href: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - the message varies per case
        validate_href(href)


def test_link_mark_in_body() -> None:
    result = cleaned(
        doc(
            para(
                text(
                    "x",
                    link("  mailto:a@example.com  ", target="_self", **{"class": None}),
                )
            )
        )
    )
    mark = result["content"][0]["content"][0]["marks"][0]
    assert mark == {
        "type": "link",
        "attrs": {"href": "mailto:a@example.com", "target": "_self"},
    }


@pytest.mark.parametrize(
    "href",
    ["javascript:alert(1)", " JAVASCRIPT:alert(1)", "data:text/html;base64,AAAA"],
)
def test_dangerous_link_rejected_in_body(href: str) -> None:
    rejects(doc(para(text("x", link(href)))), "link href must start with")


def test_link_attrs_rules() -> None:
    rejects(doc(para(text("x", {"type": "link"}))), "link needs attrs.href")
    rejects(
        doc(para(text("x", {"type": "link", "attrs": {"href": 3}}))),
        "link needs attrs.href",
    )
    rejects(doc(para(text("x", link("/a", target="_top")))), "'target'")
    rejects(doc(para(text("x", link("/a", rel=5)))), "'rel'")
    rejects(doc(para(text("x", link("/a", rel="x" * 201)))), "'rel'")
    rejects(
        doc(para(text("x", link("/a", onclick="x()")))),
        "does not allow attribute 'onclick'",
    )
    # the class attribute is dropped, not kept
    ok = cleaned(doc(para(text("x", link("/a", **{"class": "big"})))))
    assert "class" not in str(ok)


# --- size and shape limits ---


def test_rejects_oversized_body() -> None:
    rejects(doc(*[para(text("x" * 90_000)) for _ in range(12)]), "is too large")
    assert MAX_BODY_BYTES == 1_000_000


def test_size_is_measured_in_utf8_bytes() -> None:
    # 3 bytes per character: 700k characters is under 1M characters but over 1 MB.
    rejects(doc(*[para(text("中" * 70_000)) for _ in range(10)]), "is too large")


def test_rejects_too_deep_nesting() -> None:
    node: JsonDict = para(text("x"))
    for _ in range(MAX_DEPTH + 2):
        node = {"type": "blockquote", "content": [node]}
    rejects(doc(node), "nested deeper than")


def test_rejects_non_json_values() -> None:
    rejects({"type": "doc", "content": [object()]}, "must be JSON")


# --- resolved image urls ---


def test_with_image_urls_adds_src_and_keeps_original() -> None:
    other = str(uuid.uuid4())
    sanitized = sanitize_body(
        doc(
            para(text("hi")),
            image(),
            {"type": "blockquote", "content": [image(fileId=other, alt="b")]},
        )
    ).body
    snapshot = copy.deepcopy(sanitized)
    resolved: Any = with_image_urls(sanitized, "/api/v1/files/{file_id}/content")
    assert sanitized == snapshot  # input untouched
    content = resolved["content"]
    assert content[1]["attrs"] == {
        "fileId": FILE_ID,
        "src": f"/api/v1/files/{FILE_ID}/content",
    }
    assert content[2]["content"][0]["attrs"] == {
        "fileId": other,
        "alt": "b",
        "src": f"/api/v1/files/{other}/content",
    }
    assert content[0] == {
        "type": "paragraph",
        "content": [{"type": "text", "text": "hi"}],
    }


def test_with_image_urls_without_images_is_a_copy() -> None:
    body = sanitize_body(doc(para(text("x", {"type": "bold"})))).body
    assert with_image_urls(body, "/x/{file_id}") == body

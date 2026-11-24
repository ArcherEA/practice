"""Allow-list validation for the Tiptap/ProseMirror JSON body (pure, no I/O).

The body is never stored or rendered as HTML. `sanitize_body` accepts a document
only if every node, mark and attribute is on the allow-list below, and returns a
cleaned copy plus the ids of the image files it references. The database lookup
for those files lives in `service.py`.

Shape: ``{"type": "doc", "content": [...]}``; a node has ``type`` and optionally
``attrs``, ``content``, ``marks``; a text node has ``text``.
"""

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# Tiptap documents are plain JSON: objects, arrays, strings, numbers, booleans, null.
JsonDict = dict[str, object]

MAX_BODY_BYTES = 1_000_000
MAX_DEPTH = 24
MAX_TEXT_LENGTH = 100_000
MAX_HREF_LENGTH = 2048

BLOCKS = frozenset(
    {
        "paragraph",
        "heading",
        "bulletList",
        "orderedList",
        "blockquote",
        "codeBlock",
        "horizontalRule",
        "image",
    }
)
INLINES = frozenset({"text", "hardBreak"})
# Which child node types each node may contain. Nodes not listed here are leaves.
CHILDREN: dict[str, frozenset[str]] = {
    "doc": BLOCKS,
    "blockquote": BLOCKS,
    "listItem": BLOCKS,
    "bulletList": frozenset({"listItem"}),
    "orderedList": frozenset({"listItem"}),
    "paragraph": INLINES,
    "heading": INLINES,
    "codeBlock": frozenset({"text"}),
}
NODE_TYPES = BLOCKS | INLINES | {"listItem"}
MARK_TYPES = frozenset({"bold", "italic", "strike", "code", "link"})
ALLOWED_HREF_SCHEMES = frozenset({"http", "https", "mailto"})

# Attributes each node/mark type may carry. Unknown attributes are rejected, except
# when their value is null (Tiptap emits e.g. ``"class": null``), which is dropped.
NODE_ATTRS: dict[str, frozenset[str]] = {
    "heading": frozenset({"level"}),
    "orderedList": frozenset({"start", "type"}),
    "codeBlock": frozenset({"language"}),
    # `src` is accepted only to be thrown away: the server builds it from fileId.
    "image": frozenset({"fileId", "alt", "title", "src"}),
}
MARK_ATTRS: dict[str, frozenset[str]] = {
    "link": frozenset({"href", "target", "rel", "class"}),
}
ALLOWED_NODE_KEYS = frozenset({"type", "attrs", "content", "marks", "text"})


class BodyValidationError(ValueError):
    """The body is not a valid document; `path` locates the offending part."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


@dataclass
class SanitizedBody:
    body: JsonDict
    image_file_ids: set[uuid.UUID] = field(default_factory=set)


def empty_body() -> JsonDict:
    return {"type": "doc", "content": []}


def validate_href(href: str) -> str:
    """Return the trimmed `href` if it is http(s), mailto or an absolute path; else raise ValueError."""
    value = href.strip()
    if not value or len(value) > MAX_HREF_LENGTH:
        raise ValueError("link href must be 1-2048 characters")
    # Browsers drop tabs/newlines inside URLs ("java\tscript:"), so refuse control chars.
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("link href must not contain control characters")
    if value.startswith("/"):
        if value.startswith(("//", "/\\")):
            raise ValueError("link href must not be protocol-relative")
        return value
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_HREF_SCHEMES:
        shown = f"{scheme}:" if scheme else "no scheme"
        raise ValueError(
            f"link href must start with http:, https:, mailto: or / (got {shown})"
        )
    if scheme == "mailto":
        if not value[len("mailto:") :].strip():
            raise ValueError("mailto link has no address")
    elif not parts.netloc:
        raise ValueError("link href has no host")
    return value


def sanitize_body(body: Mapping[str, object]) -> SanitizedBody:
    """Validate `body` against the allow-list; return a cleaned copy and its image file ids."""
    try:
        size = len(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    except TypeError, ValueError:
        raise BodyValidationError("body", "must be JSON") from None
    if size > MAX_BODY_BYTES:
        raise BodyValidationError(
            "body", f"is too large ({size} bytes, maximum {MAX_BODY_BYTES})"
        )
    image_ids: set[uuid.UUID] = set()
    cleaned = _node(body, "doc", "body", 0, image_ids)
    return SanitizedBody(body=cleaned, image_file_ids=image_ids)


def _node(
    raw: object, parent: str, path: str, depth: int, image_ids: set[uuid.UUID]
) -> JsonDict:
    if depth > MAX_DEPTH:
        raise BodyValidationError(path, f"is nested deeper than {MAX_DEPTH} levels")
    if not isinstance(raw, Mapping):
        raise BodyValidationError(path, "must be an object")
    node_type = raw.get("type")
    if not isinstance(node_type, str):
        raise BodyValidationError(path, "needs a string 'type'")
    if depth == 0:
        if node_type != "doc":
            raise BodyValidationError(path, "root node must have type 'doc'")
    else:
        if node_type not in NODE_TYPES:
            raise BodyValidationError(path, f"unknown node type '{node_type}'")
        if node_type not in CHILDREN[parent]:
            raise BodyValidationError(
                path, f"'{node_type}' is not allowed inside '{parent}'"
            )
    extra = set(raw) - ALLOWED_NODE_KEYS
    if extra:
        raise BodyValidationError(path, f"unknown field(s): {', '.join(sorted(extra))}")

    out: JsonDict = {"type": node_type}
    attrs = _attrs(
        raw.get("attrs"), node_type, NODE_ATTRS.get(node_type, frozenset()), path
    )
    if node_type == "heading":
        level = attrs.get("level")
        if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 3:
            raise BodyValidationError(path, "heading level must be 1, 2 or 3")
    elif node_type == "orderedList":
        _check_ordered_list(attrs, path)
    elif node_type == "codeBlock":
        _check_code_block(attrs, path)
    elif node_type == "image":
        attrs = _image_attrs(attrs, path, image_ids)
    if attrs:
        out["attrs"] = attrs

    if node_type == "text":
        out["text"] = _text(raw, path)
        marks = _marks(raw.get("marks"), path)
        if marks:
            out["marks"] = marks
        if raw.get("content") is not None:
            raise BodyValidationError(path, "text nodes cannot have content")
        return out

    if "text" in raw:
        raise BodyValidationError(path, "only text nodes can have 'text'")
    if raw.get("marks"):
        raise BodyValidationError(path, "only text nodes can have marks")
    content = raw.get("content")
    if content is None:
        content = []
    if not isinstance(content, list):
        raise BodyValidationError(path, "'content' must be an array")
    if content and node_type not in CHILDREN:
        raise BodyValidationError(path, f"'{node_type}' cannot have content")
    children = [
        _node(child, node_type, f"{path}.content[{i}]", depth + 1, image_ids)
        for i, child in enumerate(content)
    ]
    if node_type == "codeBlock":
        for i, child in enumerate(children):
            if "marks" in child:
                raise BodyValidationError(
                    f"{path}.content[{i}]", "code blocks cannot contain marks"
                )
    if children or node_type == "doc":
        out["content"] = children
    return out


def _text(raw: Mapping[str, object], path: str) -> str:
    text = raw.get("text")
    if not isinstance(text, str) or not text:
        raise BodyValidationError(path, "text nodes need non-empty 'text'")
    if len(text) > MAX_TEXT_LENGTH:
        raise BodyValidationError(path, "text is too long")
    return text


def _attrs(
    raw: object, owner: str, allowed: frozenset[str], path: str
) -> dict[str, object]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise BodyValidationError(f"{path}.attrs", "must be an object")
    result: dict[str, object] = {}
    for key, value in raw.items():
        if key not in allowed:
            if value is None:
                continue
            raise BodyValidationError(
                f"{path}.attrs", f"'{owner}' does not allow attribute '{key}'"
            )
        if value is not None:
            result[key] = value
    return result


def _check_ordered_list(attrs: dict[str, object], path: str) -> None:
    start = attrs.get("start")
    if start is not None and (
        isinstance(start, bool) or not isinstance(start, int) or start < 1
    ):
        raise BodyValidationError(f"{path}.attrs", "'start' must be a positive integer")
    list_type = attrs.get("type")
    if list_type is not None and list_type not in {"1", "a", "A", "i", "I"}:
        raise BodyValidationError(f"{path}.attrs", "'type' must be 1, a, A, i or I")


def _check_code_block(attrs: dict[str, object], path: str) -> None:
    language = attrs.get("language")
    if language is None:
        return
    if (
        not isinstance(language, str)
        or len(language) > 40
        or not all(ch.isascii() and (ch.isalnum() or ch in "_+#.-") for ch in language)
    ):
        raise BodyValidationError(f"{path}.attrs", "'language' is not valid")


def _image_attrs(
    attrs: dict[str, object], path: str, image_ids: set[uuid.UUID]
) -> dict[str, object]:
    attrs = {k: v for k, v in attrs.items() if k != "src"}  # client src is ignored
    file_id = attrs.get("fileId")
    if not isinstance(file_id, str):
        raise BodyValidationError(f"{path}.attrs", "image needs attrs.fileId")
    try:
        parsed = uuid.UUID(file_id)
    except ValueError:
        raise BodyValidationError(
            f"{path}.attrs", "attrs.fileId must be a file id"
        ) from None
    image_ids.add(parsed)
    attrs["fileId"] = str(parsed)
    for key in ("alt", "title"):
        value = attrs.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > 500):
            raise BodyValidationError(
                f"{path}.attrs", f"'{key}' must be a string of at most 500 characters"
            )
    return attrs


def _marks(raw: object, path: str) -> list[JsonDict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise BodyValidationError(f"{path}.marks", "must be an array")
    result: list[JsonDict] = []
    seen: set[str] = set()
    for i, mark in enumerate(raw):
        mark_path = f"{path}.marks[{i}]"
        if not isinstance(mark, Mapping):
            raise BodyValidationError(mark_path, "must be an object")
        mark_type = mark.get("type")
        if not isinstance(mark_type, str) or mark_type not in MARK_TYPES:
            raise BodyValidationError(mark_path, f"unknown mark type '{mark_type}'")
        if set(mark) - {"type", "attrs"}:
            raise BodyValidationError(mark_path, "unknown field(s) on mark")
        if mark_type in seen:
            raise BodyValidationError(mark_path, f"duplicate '{mark_type}' mark")
        seen.add(mark_type)
        attrs = _attrs(
            mark.get("attrs"),
            mark_type,
            MARK_ATTRS.get(mark_type, frozenset()),
            mark_path,
        )
        out: JsonDict = {"type": mark_type}
        if mark_type == "link":
            attrs = _link_attrs(attrs, mark_path)
        if attrs:
            out["attrs"] = attrs
        result.append(out)
    return result


def _link_attrs(attrs: dict[str, object], path: str) -> dict[str, object]:
    href = attrs.get("href")
    if not isinstance(href, str):
        raise BodyValidationError(f"{path}.attrs", "link needs attrs.href")
    try:
        result: dict[str, object] = {"href": validate_href(href)}
    except ValueError as exc:
        raise BodyValidationError(f"{path}.attrs", str(exc)) from None
    target = attrs.get("target")
    if target is not None:
        if target not in {"_blank", "_self"}:
            raise BodyValidationError(
                f"{path}.attrs", "'target' must be _blank or _self"
            )
        result["target"] = target
    rel = attrs.get("rel")
    if rel is not None:
        if not isinstance(rel, str) or len(rel) > 200:
            raise BodyValidationError(f"{path}.attrs", "'rel' is not valid")
        result["rel"] = rel
    # `class` is dropped: classes are chosen by the renderer, not the client.
    return result


def with_image_urls(body: Mapping[str, object], url_template: str) -> JsonDict:
    """Copy of an already sanitized `body` where each image node gets ``attrs.src``.

    `url_template` has one ``{file_id}`` placeholder, e.g. ``/api/v1/files/{file_id}/content``.
    """
    return _resolve_node(body, url_template)


def _resolve_node(node: Mapping[str, object], url_template: str) -> JsonDict:
    result: JsonDict = {}
    for key, value in node.items():
        if key == "content" and isinstance(value, list):
            result[key] = [
                _resolve_node(child, url_template)
                for child in value
                if isinstance(child, Mapping)
            ]
        elif key == "attrs" and isinstance(value, Mapping):
            attrs: JsonDict = dict(value)
            file_id = attrs.get("fileId")
            if node.get("type") == "image" and isinstance(file_id, str):
                attrs["src"] = url_template.format(file_id=file_id)
            result[key] = attrs
        else:
            result[key] = value
    return result

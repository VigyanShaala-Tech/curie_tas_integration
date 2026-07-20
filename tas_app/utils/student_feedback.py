"""
Student-facing instructor comment formatting.

Strip rubric category heading blocks at display time while preserving
Quill rich-text markup for the remaining content.
"""

from __future__ import annotations

import html as html_module
import re
from html.parser import HTMLParser


_BULLET_PREFIX_RE = re.compile(r"^[\u2022*\-]\s*")
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_BLOCK_CLOSE_RE = re.compile(r"</(?:p|div|h[1-6]|li|tr)>", re.IGNORECASE)

_HEADING_BLOCK_TAGS = frozenset({"p", "div", "h1", "h2", "h3"})

_ALLOWED_TAGS = frozenset({
    "p", "br", "strong", "b", "em", "i", "u", "s", "strike", "del", "a",
    "h1", "h2", "h3", "span", "div", "ul", "ol", "li",
})
_ALLOWED_ATTRS = {
    "a": frozenset({"href", "target", "rel"}),
    "span": frozenset({"class", "style"}),
    "p": frozenset({"class", "style"}),
    "div": frozenset({"class", "style"}),
    "h1": frozenset({"class", "style"}),
    "h2": frozenset({"class", "style"}),
    "h3": frozenset({"class", "style"}),
    "ul": frozenset({"class"}),
    "ol": frozenset({"class"}),
    "li": frozenset({"class", "style", "data-list"}),
}


def is_category_heading_line(line: str) -> bool:
    """True when a line is a rubric category heading like 'Technical Accuracy:'."""
    trimmed = line.strip()
    return bool(trimmed) and trimmed.endswith(":") and ":" not in trimmed[:-1]


def looks_like_html(value: str) -> bool:
    return bool(re.search(r"<[a-z][\s\S]*>", value, re.IGNORECASE))


class _HeadingStripParser(HTMLParser):
    """Rebuild HTML while dropping block elements whose text is a category heading."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self._out: list[str] = []
        self._stack: list[dict] = []

    def handle_starttag(self, tag, attrs):
        tag_l = tag.lower()
        if tag_l == "br":
            if self._stack:
                self._stack[-1]["parts"].append("<br>")
            else:
                self._out.append("<br>")
            return

        attr_map = {k.lower(): v for k, v in attrs if k}
        self._stack.append({
            "tag": tag_l,
            "attrs": attr_map,
            "parts": [],
            "text": [],
        })

    def handle_endtag(self, tag):
        tag_l = tag.lower()
        # Find matching open tag from the end
        idx = None
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i]["tag"] == tag_l:
                idx = i
                break
        if idx is None:
            return

        # Close any nested unclosed tags after idx by flushing them first
        while len(self._stack) - 1 > idx:
            nested = self._stack.pop()
            self._emit_element(nested)

        node = self._stack.pop()
        self._emit_element(node)

    def handle_data(self, data):
        if self._stack:
            self._stack[-1]["parts"].append(data)
            self._stack[-1]["text"].append(data)
        else:
            self._out.append(data)

    def handle_entityref(self, name):
        token = f"&{name};"
        if self._stack:
            self._stack[-1]["parts"].append(token)
            self._stack[-1]["text"].append(html_module.unescape(token))
        else:
            self._out.append(token)

    def handle_charref(self, name):
        token = f"&#{name};"
        if self._stack:
            self._stack[-1]["parts"].append(token)
            self._stack[-1]["text"].append(html_module.unescape(token))
        else:
            self._out.append(token)

    def _emit_element(self, node: dict) -> None:
        tag = node["tag"]
        text = "".join(node["text"]).replace("\xa0", " ").strip()
        if tag in _HEADING_BLOCK_TAGS and is_category_heading_line(text):
            return  # drop heading block entirely

        # Drop empty p/div left after heading removal
        inner = "".join(node["parts"])
        if tag in {"p", "div"} and not text:
            return

        if tag not in _ALLOWED_TAGS:
            # unwrap disallowed tags — keep children content
            chunk = inner
        else:
            allowed = _ALLOWED_ATTRS.get(tag, frozenset())
            attr_str = ""
            for key, val in node["attrs"].items():
                if key not in allowed:
                    continue
                if tag == "a" and key == "href":
                    if not re.match(r"^(https?:|mailto:|/)", val or "", re.I):
                        continue
                escaped_val = html_module.escape(val or "", quote=True)
                attr_str += f' {key}="{escaped_val}"'
            if tag == "a":
                attr_str += ' rel="noopener noreferrer" target="_blank"'
            if tag == "br":
                chunk = "<br>"
            else:
                chunk = f"<{tag}{attr_str}>{inner}</{tag}>"

        if self._stack:
            self._stack[-1]["parts"].append(chunk)
            self._stack[-1]["text"].append(text)
        else:
            self._out.append(chunk)

    def get_html(self) -> str:
        while self._stack:
            self._emit_element(self._stack.pop())
        return "".join(self._out)


def strip_category_headings_from_comment(comment: str | None) -> str:
    """
    Remove rubric category heading blocks from a stored instructor comment.

    Returns sanitized HTML when the input is HTML; otherwise plain text with
    heading lines removed. Suitable for safe student display.
    """
    if not comment or not str(comment).strip():
        return ""

    text = str(comment)
    if not looks_like_html(text):
        lines = []
        for raw in text.splitlines():
            trimmed = raw.strip()
            if trimmed and not is_category_heading_line(trimmed):
                lines.append(raw.rstrip())
        return "\n".join(lines).strip()

    parser = _HeadingStripParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        # Fallback: strip tags to plain without headings
        return "\n".join(flatten_instructor_comment_for_student(text))

    return parser.get_html().strip()


def flatten_instructor_comment_for_student(comment: str | None) -> list[str]:
    """
    Convert stored instructor comment into plain non-heading lines.
    Kept for compatibility / tests; student UI prefers strip_category_headings_from_comment.
    """
    if not comment or not str(comment).strip():
        return []

    text = str(comment)
    text = _BR_RE.sub("\n", text)
    text = _BLOCK_CLOSE_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = html_module.unescape(text)
    text = text.replace("\xa0", " ")

    lines: list[str] = []
    for raw in text.splitlines():
        line = _BULLET_PREFIX_RE.sub("", raw).strip()
        if not line or is_category_heading_line(line):
            continue
        lines.append(line)
    return lines

"""Extract the strings a caregiver can actually read.

`static/app.js` mixes copy with selectors, wire values and element ids, and
`static/index.html` mixes copy with class names and data attributes. A plain
regex over quoted text cannot tell those apart, and an earlier version of the
workspace guard missed multi-line template literals entirely. These helpers do
the boring thing properly: a small lexer for JavaScript string literals that
understands escapes and template quasis, and an HTML parser that keeps text
nodes plus the attributes a screen reader speaks.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Attributes that are read out or shown to the caregiver.
SPOKEN_ATTRIBUTES = frozenset({"aria-label", "aria-description", "alt", "placeholder", "title"})
_SKIP_ELEMENTS = frozenset({"script", "style"})

_TAG = re.compile(r"<[^<>]*>")
_ATTRIBUTE = re.compile(r"""([\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def strip_markup(text: str) -> str:
    """Drop HTML plumbing from a JS literal, keeping the words he can read.

    Much of `static/app.js` builds markup inside string literals, so a raw
    literal mixes copy with class names, data attributes and element ids. Tags
    are removed, but the value of an attribute a screen reader speaks is kept,
    because an accessible name is copy even though it lives inside a tag.
    """

    def keep_spoken(match: re.Match[str]) -> str:
        spoken = [
            double or single
            for name, double, single in _ATTRIBUTE.findall(match.group(0))
            if name.lower() in SPOKEN_ATTRIBUTES
        ]
        return f" {' '.join(spoken)} "

    cleaned = _TAG.sub(keep_spoken, text)
    # Literals are often tag fragments, so attributes can survive tag removal.
    return _ATTRIBUTE.sub(keep_spoken, cleaned)


def javascript_string_literals(source: str) -> list[tuple[int, str]]:
    """Return `(line number, literal text)` for every JS string literal.

    Template literals contribute their static quasis only; a `${...}`
    expression is skipped so embedded identifiers are never mistaken for copy.
    Nested templates inside an expression are still scanned, because that is
    exactly where accessible names were hiding.
    """

    results: list[tuple[int, str]] = []
    index = 0
    line = 1
    length = len(source)
    previous = ""
    while index < length:
        char = source[index]
        if char == "\n":
            line += 1
            index += 1
            continue
        if char == "/" and index + 1 < length and source[index + 1] in "/*":
            index, line = _skip_comment(source, index, line)
            continue
        if char == "/" and _regex_may_start_here(source, index, previous):
            index, line = _skip_regex(source, index, line)
            previous = "/"
            continue
        if char in "'\"":
            index, line, text = _read_quoted(source, index, line, char)
            results.append((line, text))
            previous = char
            continue
        if char == "`":
            index, line, quasis = _read_template(source, index, line)
            results.extend(quasis)
            previous = "`"
            continue
        if not char.isspace():
            previous = char
        index += 1
    return results


# A `/` right after one of these cannot be division, so it opens a regex.
_REGEX_PREDECESSORS = frozenset("(,=:[!&|?{};+-*%~^<>")

# Nor can it be division right after a keyword: `return /['"]/` is a regex, and
# reading it as division swallows the next real string literal whole, which is
# precisely how a guard goes quietly blind.
_REGEX_KEYWORDS = frozenset(
    {
        "return",
        "typeof",
        "instanceof",
        "in",
        "of",
        "new",
        "delete",
        "void",
        "case",
        "do",
        "else",
        "yield",
        "await",
        "throw",
    }
)
_TRAILING_WORD = re.compile(r"[A-Za-z_$][\w$]*$")


def _regex_may_start_here(source: str, index: int, previous: str) -> bool:
    if previous == "" or previous in _REGEX_PREDECESSORS:
        return True
    if not previous.isalnum() and previous not in "_$":
        return False
    word = _TRAILING_WORD.search(source[:index].rstrip())
    return bool(word) and word.group(0) in _REGEX_KEYWORDS


def _skip_comment(source: str, index: int, line: int) -> tuple[int, int]:
    if source[index + 1] == "/":
        end = source.find("\n", index)
        return (len(source), line) if end == -1 else (end, line)
    end = source.find("*/", index + 2)
    stop = len(source) if end == -1 else end + 2
    return stop, line + source.count("\n", index, stop)


def _skip_regex(source: str, index: int, line: int) -> tuple[int, int]:
    index += 1
    in_class = False
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == "\n":
            # An unterminated regex means the `/` was division after all.
            return index, line
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            index += 1
            break
        index += 1
    return index, line


def _read_quoted(source: str, index: int, line: int, quote: str) -> tuple[int, int, str]:
    index += 1
    buffer: list[str] = []
    while index < len(source):
        char = source[index]
        if char == "\\":
            buffer.append(source[index : index + 2])
            index += 2
            continue
        if char == quote:
            index += 1
            break
        if char == "\n":
            line += 1
        buffer.append(char)
        index += 1
    return index, line, _unescape("".join(buffer))


def _read_template(source: str, index: int, line: int) -> tuple[int, int, list[tuple[int, str]]]:
    index += 1
    found: list[tuple[int, str]] = []
    buffer: list[str] = []
    quasi_line = line
    while index < len(source):
        char = source[index]
        if char == "\\":
            buffer.append(source[index : index + 2])
            index += 2
            continue
        if char == "`":
            index += 1
            break
        if char == "$" and index + 1 < len(source) and source[index + 1] == "{":
            found.append((quasi_line, _unescape("".join(buffer))))
            buffer = []
            index, line, nested = _skip_expression(source, index + 2, line)
            found.extend(nested)
            quasi_line = line
            continue
        if char == "\n":
            line += 1
        buffer.append(char)
        index += 1
    found.append((quasi_line, _unescape("".join(buffer))))
    return index, line, found


def _skip_expression(source: str, index: int, line: int) -> tuple[int, int, list[tuple[int, str]]]:
    """Walk to the matching `}` of a template expression, collecting strings.

    A `${...}` expression is code, but conditional copy lives there constantly
    — `${x === null ? 'No title recorded' : x}` is a sentence he reads. The
    strings are therefore returned rather than thrown away; only the
    identifiers and operators around them are dropped.
    """

    depth = 1
    previous = "{"
    found: list[tuple[int, str]] = []
    while index < len(source) and depth:
        char = source[index]
        if char == "\n":
            line += 1
            index += 1
            continue
        if char == "/" and index + 1 < len(source) and source[index + 1] in "/*":
            index, line = _skip_comment(source, index, line)
            continue
        if char == "/" and _regex_may_start_here(source, index, previous):
            index, line = _skip_regex(source, index, line)
            previous = "/"
            continue
        if char in "'\"":
            index, line, text = _read_quoted(source, index, line, char)
            found.append((line, text))
            previous = char
            continue
        if char == "`":
            index, line, quasis = _read_template(source, index, line)
            found.extend(quasis)
            previous = "`"
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if not char.isspace():
            previous = char
        index += 1
    return index, line, found


def _unescape(text: str) -> str:
    return (
        text.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\'", "'")
        .replace('\\"', '"')
        .replace("\\`", "`")
        .replace("\\\\", "\\")
    )


def javascript_interpolations(source: str) -> list[tuple[int, str]]:
    """Return `(line number, expression text)` for every `${...}` in a template.

    The copy scanner deliberately throws template expressions away, because it
    is looking for words. A date guard needs the opposite: the expressions are
    where a stored value is read, and reading one without a formatter is exactly
    how a machine date reaches the screen. Nested templates contribute their own
    expressions too, so a conditional inside an interpolation is still seen.
    """

    found: list[tuple[int, str]] = []
    index = 0
    line = 1
    length = len(source)
    previous = ""
    while index < length:
        char = source[index]
        if char == "\n":
            line += 1
            index += 1
            continue
        if char == "/" and index + 1 < length and source[index + 1] in "/*":
            index, line = _skip_comment(source, index, line)
            continue
        if char == "/" and _regex_may_start_here(source, index, previous):
            index, line = _skip_regex(source, index, line)
            previous = "/"
            continue
        if char in "'\"":
            index, line, _ = _read_quoted(source, index, line, char)
            previous = char
            continue
        if char == "`":
            index, line = _collect_interpolations(source, index, line, found)
            previous = "`"
            continue
        if not char.isspace():
            previous = char
        index += 1
    return found


def _collect_interpolations(
    source: str, index: int, line: int, found: list[tuple[int, str]]
) -> tuple[int, int]:
    index += 1
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == "`":
            return index + 1, line
        if char == "$" and index + 1 < len(source) and source[index + 1] == "{":
            start = index + 2
            opened = line
            index, line, _ = _skip_expression(source, start, line)
            # `_skip_expression` stops just past the closing brace.
            found.append((opened, source[start : index - 1]))
            continue
        if char == "\n":
            line += 1
        index += 1
    return index, line


class _VisibleHtml(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._open: list[str] = []
        self.strings: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):
        self._open.append(tag)
        for name, value in attrs:
            if name in SPOKEN_ATTRIBUTES and value and value.strip():
                self.strings.append((self.getpos()[0], value.strip()))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self._open:
            self._open.pop()

    def handle_endtag(self, tag):
        if tag in self._open:
            while self._open and self._open.pop() != tag:
                pass

    def handle_data(self, data):
        if any(tag in _SKIP_ELEMENTS for tag in self._open):
            return
        text = data.strip()
        if text:
            self.strings.append((self.getpos()[0], text))


def html_visible_strings(source: str) -> list[tuple[int, str]]:
    """Return `(line number, text)` for HTML copy and spoken attributes."""

    parser = _VisibleHtml()
    parser.feed(source)
    return parser.strings

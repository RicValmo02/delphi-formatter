"""Minimal parser for Delphi's text ``.dfm`` resource files.

Why parse DFMs at all? When the formatter renames a field in a form class
(e.g. ``Button1`` -> ``btnButton1``), the sibling ``.dfm`` declares the
same identifier as a component name (``object Button1: TButton``) and may
reference it from other components' properties (``PopupMenu = pmMain``).
Renaming the ``.pas`` without updating the ``.dfm`` silently breaks the
runtime binding.

This module stays deliberately small:

* Lex the textual DFM (binary DFMs are only detected and rejected — see
  :func:`is_binary_dfm`).
* Build a light-weight AST with enough position info to support **positional
  rewrites**: we never re-emit the DFM, we splice strings at known offsets,
  so indentation / comments / weird whitespace are preserved byte-for-byte.
* Expose :func:`apply_rename` which takes a rename map and returns the
  updated DFM text (same text if nothing in the map applies).

Grammar (text DFM):

    object_decl := ("object" | "inline" | "inherited") NAME ':' TYPE_NAME
                   (property | object_decl)* 'end'
    property    := NAME ('.' NAME)* '=' value
    value       := STRING | NUMBER | NAME | '[' set_items ']'
                 | '<' collection ']' | '{' hex_bytes '}'

We're deliberately permissive: the parser degrades gracefully on unexpected
tokens rather than raising, because its job is rename propagation, not
syntax validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Binary-DFM detection
# ---------------------------------------------------------------------------


def is_binary_dfm(data: bytes) -> bool:
    """True if *data* looks like a binary (not-textual) DFM resource.

    Delphi's binary DFMs start with the magic bytes ``TPF0``. The textual
    form starts with ``object`` / ``inherited`` / ``inline`` (or a BOM).
    Binary DFMs need to be converted to text with ``convert.exe`` before
    the formatter can touch them.
    """
    return len(data) >= 4 and data[:4] == b"TPF0"


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


# Token kinds.
_NAME = "NAME"
_NUMBER = "NUMBER"
_STRING = "STRING"
_LBRACK = "LBRACK"
_RBRACK = "RBRACK"
_LANGLE = "LANGLE"
_RANGLE = "RANGLE"
_LBRACE = "LBRACE"
_RBRACE = "RBRACE"
_EQUALS = "EQUALS"
_COMMA = "COMMA"
_COLON = "COLON"
_DOT = "DOT"
_PLUS = "PLUS"
_EOF = "EOF"


@dataclass
class _DfmToken:
    kind: str
    value: str
    start: int
    end: int  # exclusive


def _is_name_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_name_cont(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _tokenize(text: str) -> list[_DfmToken]:
    tokens: list[_DfmToken] = []
    i = 0
    n = len(text)
    # Skip a leading BOM if present so our offsets match the passed-in text.
    if n >= 1 and text[0] == "\ufeff":
        i = 1

    while i < n:
        ch = text[i]

        # Whitespace and newlines
        if ch in " \t\r\n":
            i += 1
            continue

        # Line comments (rare in DFM but legal).
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue

        # Strings — including concatenations with #NN char-codes.
        # Delphi DFM lets you write 'abc'#13#10'def' as a single value, so
        # we greedily consume runs of ('...' | #<digits>) separated by nothing
        # or whitespace. Note that `+` can also concatenate strings; we
        # handle that at the parser level.
        if ch == "'" or ch == "#":
            start = i
            while i < n:
                c = text[i]
                if c == "'":
                    # consume the literal, including escaped ''.
                    i += 1
                    while i < n:
                        if text[i] == "'":
                            if i + 1 < n and text[i + 1] == "'":
                                i += 2  # escaped quote
                                continue
                            i += 1
                            break
                        i += 1
                    continue
                if c == "#":
                    i += 1
                    # '#' may be followed by decimal digits or a '$'-hex.
                    if i < n and text[i] == "$":
                        i += 1
                        while i < n and text[i] in "0123456789abcdefABCDEF":
                            i += 1
                    else:
                        while i < n and text[i].isdigit():
                            i += 1
                    continue
                break
            tokens.append(_DfmToken(_STRING, text[start:i], start, i))
            continue

        # Numbers (integer, float, hex, negative)
        if ch.isdigit() or (ch == "-" and i + 1 < n and text[i + 1].isdigit()):
            start = i
            if ch == "-":
                i += 1
            while i < n and (text[i].isdigit() or text[i] in ".eE+-"):
                # careful with + / -: only inside exponent
                c2 = text[i]
                if c2 in "+-":
                    prev = text[i - 1]
                    if prev not in "eE":
                        break
                i += 1
            tokens.append(_DfmToken(_NUMBER, text[start:i], start, i))
            continue
        if ch == "$":  # hex literal
            start = i
            i += 1
            while i < n and text[i] in "0123456789abcdefABCDEF":
                i += 1
            tokens.append(_DfmToken(_NUMBER, text[start:i], start, i))
            continue

        # Identifiers / names
        if _is_name_start(ch):
            start = i
            i += 1
            while i < n and _is_name_cont(text[i]):
                i += 1
            tokens.append(_DfmToken(_NAME, text[start:i], start, i))
            continue

        # Punctuation
        if ch == "[":
            tokens.append(_DfmToken(_LBRACK, ch, i, i + 1)); i += 1; continue
        if ch == "]":
            tokens.append(_DfmToken(_RBRACK, ch, i, i + 1)); i += 1; continue
        if ch == "<":
            tokens.append(_DfmToken(_LANGLE, ch, i, i + 1)); i += 1; continue
        if ch == ">":
            tokens.append(_DfmToken(_RANGLE, ch, i, i + 1)); i += 1; continue
        if ch == "{":
            # Binary hex block, e.g. Picture.Data = { 01 02 03 }. Consume it
            # whole — opaque to us.
            start = i
            i += 1
            while i < n and text[i] != "}":
                i += 1
            if i < n:
                i += 1  # consume '}'
            tokens.append(_DfmToken(_LBRACE, text[start:i], start, i))
            continue
        if ch == "}":
            tokens.append(_DfmToken(_RBRACE, ch, i, i + 1)); i += 1; continue
        if ch == "=":
            tokens.append(_DfmToken(_EQUALS, ch, i, i + 1)); i += 1; continue
        if ch == ",":
            tokens.append(_DfmToken(_COMMA, ch, i, i + 1)); i += 1; continue
        if ch == ":":
            tokens.append(_DfmToken(_COLON, ch, i, i + 1)); i += 1; continue
        if ch == ".":
            tokens.append(_DfmToken(_DOT, ch, i, i + 1)); i += 1; continue
        if ch == "+":
            tokens.append(_DfmToken(_PLUS, ch, i, i + 1)); i += 1; continue

        # Unknown character — skip to stay resilient.
        i += 1

    tokens.append(_DfmToken(_EOF, "", n, n))
    return tokens


# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------


# Value kinds we care about when applying renames.
VK_STRING = "STRING"
VK_NUMBER = "NUMBER"
VK_BARE_IDENT = "BARE_IDENT"
VK_SET = "SET"
VK_COLLECTION = "COLLECTION"
VK_BINARY = "BINARY"
VK_UNKNOWN = "UNKNOWN"


@dataclass
class DfmProperty:
    """A ``Name = value`` pair inside an object body."""
    name: str              # full dotted name, e.g. 'Font.Size' or 'OnClick'
    name_span: tuple[int, int]
    value_kind: str        # one of VK_*
    value_text: str        # literal text of the value, for rename matching
    value_start: int       # offset of the value's first char (after '=' and ws)
    value_end: int         # exclusive
    is_event: bool         # last dotted segment starts with 'On' (case-insensitive)


@dataclass
class DfmObject:
    """A DFM ``object Name: Type ... end`` block (or ``inline``/``inherited``)."""
    header_kind: str       # 'object' | 'inline' | 'inherited'
    name: str
    name_span: tuple[int, int]
    type_name: str
    type_span: tuple[int, int]
    body_start: int        # offset just after the header line
    body_end: int          # offset of the 'end' keyword
    properties: list[DfmProperty] = field(default_factory=list)
    children: list["DfmObject"] = field(default_factory=list)


class DfmParseError(Exception):
    """Raised by :func:`parse_dfm` when the input can't be recognised as a
    textual DFM at all (e.g. empty or not starting with a valid header)."""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


_OBJECT_HEADERS = {"object", "inline", "inherited"}


@dataclass
class _ParseState:
    tokens: list[_DfmToken]
    idx: int = 0

    def peek(self, offset: int = 0) -> _DfmToken:
        k = self.idx + offset
        if k >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[k]

    def advance(self) -> _DfmToken:
        t = self.tokens[self.idx]
        if self.idx + 1 < len(self.tokens):
            self.idx += 1
        return t


def parse_dfm(text: str) -> DfmObject:
    """Parse *text* as a textual DFM. Returns the root object.

    Raises :class:`DfmParseError` if *text* doesn't start with a valid
    object header — the caller can treat that as "not a DFM we understand"
    and skip rewriting.
    """
    st = _ParseState(_tokenize(text))
    # Find the first object header (allow stray whitespace/comments already
    # consumed by the lexer, but nothing meaningful before).
    first = st.peek()
    if first.kind != _NAME or first.value.lower() not in _OBJECT_HEADERS:
        raise DfmParseError(
            f"expected 'object'/'inline'/'inherited' at offset {first.start}, "
            f"got {first.kind} {first.value!r}"
        )
    return _parse_object(st)


def _parse_dotted_name(st: _ParseState) -> tuple[str, tuple[int, int]]:
    """Consume ``NAME (DOT NAME)*`` and return the joined name + its span."""
    first = st.advance()
    start = first.start
    end = first.end
    parts = [first.value]
    while st.peek().kind == _DOT and st.peek(1).kind == _NAME:
        st.advance()  # DOT
        nxt = st.advance()
        parts.append(nxt.value)
        end = nxt.end
    return ".".join(parts), (start, end)


def _parse_object(st: _ParseState) -> DfmObject:
    header_tok = st.advance()
    header_kind = header_tok.value.lower()

    # Name: IDENT (dotted names aren't legal here, but cost nothing to allow)
    name_tok = st.advance()
    if name_tok.kind != _NAME:
        raise DfmParseError(
            f"expected object name at offset {name_tok.start}"
        )
    name = name_tok.value
    name_span = (name_tok.start, name_tok.end)

    # Colon
    colon = st.advance()
    if colon.kind != _COLON:
        # Permissive: continue without type_name if we can.
        type_name = ""
        type_span = (colon.start, colon.start)
    else:
        type_tok = st.advance()
        if type_tok.kind != _NAME:
            type_name = ""
            type_span = (type_tok.start, type_tok.start)
        else:
            type_name, type_span = _collect_qualified_type(st, type_tok)

    body_start = st.peek().start
    properties: list[DfmProperty] = []
    children: list[DfmObject] = []

    while True:
        t = st.peek()
        if t.kind == _EOF:
            body_end = t.start
            break
        if t.kind == _NAME and t.value.lower() == "end":
            body_end = t.start
            st.advance()
            break
        if t.kind == _NAME and t.value.lower() in _OBJECT_HEADERS:
            children.append(_parse_object(st))
            continue
        if t.kind == _NAME:
            prop = _maybe_parse_property(st)
            if prop is not None:
                properties.append(prop)
                continue
        # Unrecognised token — skip to stay resilient.
        st.advance()

    return DfmObject(
        header_kind=header_kind,
        name=name,
        name_span=name_span,
        type_name=type_name,
        type_span=type_span,
        body_start=body_start,
        body_end=body_end,
        properties=properties,
        children=children,
    )


def _collect_qualified_type(
    st: _ParseState, first: _DfmToken
) -> tuple[str, tuple[int, int]]:
    """Type names are almost always a single ident, but we accept dotted
    forms defensively (``Unit.TFoo``)."""
    start, end = first.start, first.end
    parts = [first.value]
    while st.peek().kind == _DOT and st.peek(1).kind == _NAME:
        st.advance()
        nxt = st.advance()
        parts.append(nxt.value)
        end = nxt.end
    return ".".join(parts), (start, end)


def _maybe_parse_property(st: _ParseState) -> DfmProperty | None:
    # Snapshot in case we need to bail without consuming.
    saved = st.idx
    name, name_span = _parse_dotted_name(st)
    if st.peek().kind != _EQUALS:
        st.idx = saved
        return None
    st.advance()  # '='
    value_kind, value_text, value_start, value_end = _parse_value(st)
    last_seg = name.rsplit(".", 1)[-1]
    is_event = last_seg.lower().startswith("on")
    return DfmProperty(
        name=name,
        name_span=name_span,
        value_kind=value_kind,
        value_text=value_text,
        value_start=value_start,
        value_end=value_end,
        is_event=is_event,
    )


def _parse_value(st: _ParseState) -> tuple[str, str, int, int]:
    """Consume a property value and return (kind, text, start, end).

    ``text`` and the span cover the full (possibly multi-token) value — for
    strings, the concatenation chain; for sets, the ``[...]`` including
    brackets; and so on. Only bare identifiers ever end up as rename
    candidates, but we record spans for every kind so callers can inspect
    them if they want.
    """
    t = st.peek()

    if t.kind == _STRING:
        start = t.start
        end = t.end
        st.advance()
        # Optional string concatenation: 'abc' + 'def' or 'abc' #13 'def'
        while True:
            nxt = st.peek()
            if nxt.kind == _PLUS and st.peek(1).kind == _STRING:
                st.advance()  # '+'
                nxt2 = st.advance()
                end = nxt2.end
                continue
            if nxt.kind == _STRING:
                st.advance()
                end = nxt.end
                continue
            break
        return VK_STRING, "", start, end

    if t.kind == _NUMBER:
        st.advance()
        return VK_NUMBER, t.value, t.start, t.end

    if t.kind == _LBRACE:
        st.advance()
        return VK_BINARY, "", t.start, t.end

    if t.kind == _LBRACK:
        start = t.start
        st.advance()
        depth = 1
        end = t.end
        while depth > 0:
            nxt = st.peek()
            if nxt.kind == _EOF:
                break
            if nxt.kind == _LBRACK:
                depth += 1
            elif nxt.kind == _RBRACK:
                depth -= 1
                end = nxt.end
                st.advance()
                if depth == 0:
                    break
                continue
            end = nxt.end
            st.advance()
        return VK_SET, "", start, end

    if t.kind == _LANGLE:
        start = t.start
        st.advance()
        depth = 1
        end = t.end
        # A collection contains pseudo-objects ``item ... end``. We skip
        # past them token by token; since 'end' is shared we need to treat
        # the outer '>' as the delimiter rather than nested 'end's. Keep
        # it simple: consume until matching '>' at depth 1, handling nested
        # '<' just in case.
        while depth > 0:
            nxt = st.peek()
            if nxt.kind == _EOF:
                break
            if nxt.kind == _LANGLE:
                depth += 1
            elif nxt.kind == _RANGLE:
                depth -= 1
                end = nxt.end
                st.advance()
                if depth == 0:
                    break
                continue
            end = nxt.end
            st.advance()
        return VK_COLLECTION, "", start, end

    if t.kind == _NAME:
        # Bare identifier — possibly qualified (e.g. alClient, True, False,
        # or 'Module1.Field' — rare).
        name, span = _parse_dotted_name(st)
        return VK_BARE_IDENT, name, span[0], span[1]

    # Unrecognised — consume one token so we don't spin.
    st.advance()
    return VK_UNKNOWN, t.value, t.start, t.end


# ---------------------------------------------------------------------------
# Rename application
# ---------------------------------------------------------------------------


def apply_rename(
    dfm_text: str,
    root: DfmObject,
    rename_map: dict[str, str],
) -> str:
    """Return *dfm_text* with identifier rewrites applied, or the original
    text if nothing matches.

    Only two kinds of spans are candidates:

    * the ``Name`` in ``object Name: Type`` (recursed into children).
    * the RHS of a property whose value is a single bare identifier
      (``DataSource = DataSource1``) — but NEVER if the property name's
      last dotted segment starts with ``On`` (event handlers point at
      methods, not fields).

    Matching is case-insensitive; the replacement uses the exact spelling
    from *rename_map*'s values.
    """
    if not rename_map:
        return dfm_text

    lower_map = {k.lower(): v for k, v in rename_map.items()}
    edits: list[tuple[int, int, str]] = []

    def visit(obj: DfmObject) -> None:
        key = obj.name.lower()
        if key in lower_map:
            edits.append((obj.name_span[0], obj.name_span[1], lower_map[key]))
        for p in obj.properties:
            if p.is_event:
                continue
            if p.value_kind != VK_BARE_IDENT:
                continue
            vkey = p.value_text.lower()
            if vkey in lower_map:
                edits.append((p.value_start, p.value_end, lower_map[vkey]))
        for c in obj.children:
            visit(c)

    visit(root)

    if not edits:
        return dfm_text

    # Apply in descending offset order so earlier edits don't shift later ones.
    edits.sort(key=lambda e: e[0], reverse=True)
    buf = dfm_text
    for start, end, new in edits:
        buf = buf[:start] + new + buf[end:]
    return buf


__all__ = [
    "DfmObject",
    "DfmProperty",
    "DfmParseError",
    "apply_rename",
    "is_binary_dfm",
    "parse_dfm",
    "VK_BARE_IDENT",
    "VK_STRING",
    "VK_NUMBER",
    "VK_SET",
    "VK_COLLECTION",
    "VK_BINARY",
    "VK_UNKNOWN",
]

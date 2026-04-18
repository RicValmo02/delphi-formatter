"""Tokenizer for Delphi / Object Pascal.

The tokenizer produces a flat list of :class:`Token` objects that together
cover the entire source text byte-for-byte (including whitespace, newlines
and comments). This is by design: later formatting passes rewrite token
*values* (e.g. to change casing or rename identifiers) and then re-emit the
source by concatenating ``token.value`` for every token.

Token types
-----------
- ``IDENT``     identifier (may later be reclassified as KEYWORD)
- ``KEYWORD``   reserved word (set after classification)
- ``NUMBER``    integer / float / ``$hex`` / ``%bin``
- ``STRING``    ``'text'`` plus optional ``#nn`` char codes
- ``OPERATOR``  punctuation / operators (``:=``, ``<>``, ``,``, ...)
- ``COMMENT``   ``//...`` , ``{...}`` , ``(*...*)``
- ``DIRECTIVE`` ``{$...}`` compiler directive
- ``WHITESPACE`` runs of spaces/tabs (no newline)
- ``NEWLINE``   one line terminator (\\n or \\r\\n), normalised to \\n in value
- ``EOF``       sentinel at end of stream
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from .keywords import is_keyword


IDENT = "IDENT"
KEYWORD = "KEYWORD"
NUMBER = "NUMBER"
STRING = "STRING"
OPERATOR = "OPERATOR"
COMMENT = "COMMENT"
DIRECTIVE = "DIRECTIVE"
WHITESPACE = "WHITESPACE"
NEWLINE = "NEWLINE"
EOF = "EOF"


@dataclass
class Token:
    type: str
    value: str
    line: int
    col: int

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"Token({self.type!r}, {self.value!r}, line={self.line}, col={self.col})"


class TokenizerError(ValueError):
    pass


_IDENT_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
_IDENT_CONT = _IDENT_START | set("0123456789")
_DIGITS = set("0123456789")


def tokenize(source: str) -> list[Token]:
    """Tokenise *source* into a list of Tokens covering the full input."""
    tokens: list[Token] = []
    i = 0
    line = 1
    col = 1
    n = len(source)

    def peek(offset: int = 0) -> str:
        j = i + offset
        return source[j] if j < n else ""

    def emit(tok_type: str, value: str, tl: int, tc: int) -> None:
        tokens.append(Token(tok_type, value, tl, tc))

    while i < n:
        start = i
        start_line = line
        start_col = col
        ch = source[i]

        # --- newline (preserve as single \n token) ----------------------
        if ch == "\r":
            # Normalise CRLF or bare CR to "\n" on the token value.
            if peek(1) == "\n":
                emit(NEWLINE, "\n", start_line, start_col)
                i += 2
            else:
                emit(NEWLINE, "\n", start_line, start_col)
                i += 1
            line += 1
            col = 1
            continue
        if ch == "\n":
            emit(NEWLINE, "\n", start_line, start_col)
            i += 1
            line += 1
            col = 1
            continue

        # --- whitespace run (spaces and tabs only) ----------------------
        if ch == " " or ch == "\t":
            while i < n and source[i] in (" ", "\t"):
                i += 1
            value = source[start:i]
            emit(WHITESPACE, value, start_line, start_col)
            col += len(value)
            continue

        # --- line comment -----------------------------------------------
        if ch == "/" and peek(1) == "/":
            while i < n and source[i] not in ("\r", "\n"):
                i += 1
            value = source[start:i]
            emit(COMMENT, value, start_line, start_col)
            col += len(value)
            continue

        # --- brace comment / directive ----------------------------------
        if ch == "{":
            end = source.find("}", i + 1)
            if end == -1:
                raise TokenizerError(f"Unterminated brace comment at line {line}")
            value = source[i : end + 1]
            is_dir = len(value) >= 3 and value[1] == "$"
            tok_type = DIRECTIVE if is_dir else COMMENT
            emit(tok_type, value, start_line, start_col)
            # Update line/col based on the span consumed
            nl_count = value.count("\n")
            if nl_count:
                line += nl_count
                col = len(value) - value.rfind("\n")
            else:
                col += len(value)
            i = end + 1
            continue

        # --- paren-star comment / directive -----------------------------
        if ch == "(" and peek(1) == "*":
            end = source.find("*)", i + 2)
            if end == -1:
                raise TokenizerError(f"Unterminated (* *) comment at line {line}")
            value = source[i : end + 2]
            is_dir = len(value) >= 4 and value[2] == "$"
            tok_type = DIRECTIVE if is_dir else COMMENT
            emit(tok_type, value, start_line, start_col)
            nl_count = value.count("\n")
            if nl_count:
                line += nl_count
                col = len(value) - value.rfind("\n")
            else:
                col += len(value)
            i = end + 2
            continue

        # --- string literal (with optional #nn char codes concatenated) -
        if ch == "'" or ch == "#":
            j = i
            while j < n:
                c = source[j]
                if c == "'":
                    # quoted segment: handle '' escape
                    j += 1
                    while j < n:
                        if source[j] == "'":
                            if j + 1 < n and source[j + 1] == "'":
                                j += 2
                                continue
                            j += 1
                            break
                        if source[j] in ("\r", "\n"):
                            raise TokenizerError(
                                f"Unterminated string literal at line {start_line}"
                            )
                        j += 1
                    else:
                        raise TokenizerError(
                            f"Unterminated string literal at line {start_line}"
                        )
                    continue
                if c == "#":
                    # char code, optionally $hex
                    j += 1
                    if j < n and source[j] == "$":
                        j += 1
                        while j < n and source[j] in "0123456789abcdefABCDEF":
                            j += 1
                    else:
                        while j < n and source[j] in _DIGITS:
                            j += 1
                    continue
                break
            value = source[i:j]
            if not value:
                raise TokenizerError(
                    f"Invalid string/char literal at line {start_line}"
                )
            emit(STRING, value, start_line, start_col)
            col += len(value)
            i = j
            continue

        # --- hex / binary number ----------------------------------------
        if ch == "$":
            j = i + 1
            while j < n and source[j] in "0123456789abcdefABCDEF":
                j += 1
            if j == i + 1:
                # lone $ — treat as operator so we don't choke
                emit(OPERATOR, "$", start_line, start_col)
                col += 1
                i = j
                continue
            value = source[i:j]
            emit(NUMBER, value, start_line, start_col)
            col += len(value)
            i = j
            continue
        if ch == "%":
            j = i + 1
            while j < n and source[j] in "01":
                j += 1
            if j > i + 1:
                value = source[i:j]
                emit(NUMBER, value, start_line, start_col)
                col += len(value)
                i = j
                continue
            # otherwise fall through to operators

        # --- decimal number ---------------------------------------------
        if ch in _DIGITS:
            j = i
            while j < n and source[j] in _DIGITS:
                j += 1
            # fractional part (but not '..' range operator)
            if j < n and source[j] == "." and peek(j - i + 1) != ".":
                j += 1
                while j < n and source[j] in _DIGITS:
                    j += 1
            # exponent
            if j < n and source[j] in ("e", "E"):
                j += 1
                if j < n and source[j] in ("+", "-"):
                    j += 1
                while j < n and source[j] in _DIGITS:
                    j += 1
            value = source[i:j]
            emit(NUMBER, value, start_line, start_col)
            col += len(value)
            i = j
            continue

        # --- identifier / keyword ---------------------------------------
        if ch in _IDENT_START or ch == "&":
            j = i
            if ch == "&":  # escaped identifier, e.g. &begin
                j += 1
            while j < n and source[j] in _IDENT_CONT:
                j += 1
            value = source[i:j]
            if len(value) > 0 and (value[0] == "&" or value[0] in _IDENT_START):
                name = value.lstrip("&")
                # Only actual reserved words get the KEYWORD token type.
                # "Directives" (override, virtual, strict, message, read, write,
                # ...) are contextual — they're only keywords in specific
                # positions and are perfectly valid identifier names elsewhere.
                tok_type = KEYWORD if is_keyword(name) else IDENT
                emit(tok_type, value, start_line, start_col)
                col += len(value)
                i = j
                continue

        # --- multi-char operators ---------------------------------------
        two = source[i : i + 2]
        if two in (":=", "<>", "<=", ">=", "..", "+=", "-=", "*=", "/="):
            emit(OPERATOR, two, start_line, start_col)
            i += 2
            col += 2
            continue

        # --- single-char operators --------------------------------------
        if ch in "+-*/=<>.,;:()[]^@":
            emit(OPERATOR, ch, start_line, start_col)
            i += 1
            col += 1
            continue

        raise TokenizerError(
            f"Unexpected character {ch!r} at line {line}, col {col}"
        )

    emit(EOF, "", line, col)
    return tokens


def detokenize(tokens: list[Token]) -> str:
    """Reassemble source text from a token list. Inverse of :func:`tokenize`."""
    return "".join(tok.value for tok in tokens if tok.type != EOF)


def iter_significant(tokens: list[Token]) -> Iterator[tuple[int, Token]]:
    """Yield (index, token) pairs skipping whitespace/newline/comment/directive."""
    for idx, tok in enumerate(tokens):
        if tok.type not in (WHITESPACE, NEWLINE, COMMENT, DIRECTIVE, EOF):
            yield idx, tok

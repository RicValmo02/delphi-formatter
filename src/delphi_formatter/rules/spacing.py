"""Whitespace-around-operators pass.

Operates on the token list. Inserts / removes ``WHITESPACE`` tokens so that
configured spacing rules hold. Does not touch existing newlines.
"""

from __future__ import annotations

from typing import Any

from ..tokenizer import NEWLINE, OPERATOR, WHITESPACE, Token


_BINARY_OPS = {":=", "=", "<>", "<=", ">=", "+=", "-=", "*=", "/="}


def _is_blank_ish(tok: Token | None) -> bool:
    return tok is not None and tok.type in (WHITESPACE, NEWLINE)


def apply(tokens: list[Token], config: dict[str, Any]) -> None:
    sp = config.get("spacing", {}) or {}
    do_ops = bool(sp.get("aroundOperators", True))
    do_comma = bool(sp.get("afterComma", True))
    no_space_before_semi = not bool(sp.get("beforeSemicolon", False))

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if do_ops and tok.type == OPERATOR and tok.value in _BINARY_OPS:
            # Ensure a single space before (unless at start of line)
            prev = tokens[i - 1] if i > 0 else None
            if prev is not None and prev.type != WHITESPACE and prev.type != NEWLINE:
                tokens.insert(i, Token(WHITESPACE, " ", tok.line, tok.col))
                i += 1
            elif prev is not None and prev.type == WHITESPACE and prev.value != " ":
                prev.value = " "
            # Ensure a single space after (unless end of line)
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            if nxt is not None and nxt.type != WHITESPACE and nxt.type != NEWLINE:
                tokens.insert(i + 1, Token(WHITESPACE, " ", tok.line, tok.col))
            elif nxt is not None and nxt.type == WHITESPACE and nxt.value != " ":
                nxt.value = " "

        elif do_comma and tok.type == OPERATOR and tok.value == ",":
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            if nxt is not None and nxt.type not in (WHITESPACE, NEWLINE):
                tokens.insert(i + 1, Token(WHITESPACE, " ", tok.line, tok.col))

        elif no_space_before_semi and tok.type == OPERATOR and tok.value == ";":
            prev = tokens[i - 1] if i > 0 else None
            if prev is not None and prev.type == WHITESPACE:
                # Remove the whitespace before ';'
                del tokens[i - 1]
                i -= 1

        i += 1

"""Whitespace-around-operators pass.

Operates on the token list. Inserts / removes ``WHITESPACE`` tokens so that
configured spacing rules hold. Does not touch existing newlines.

Config (under the top-level ``spacing`` key):

* ``aroundOperators``        — generic binary operators (``=``, ``<>``,
  ``<=``, ``>=``, ``+=``, ``-=``, ``*=``, ``/=``). Does **not** cover
  ``:=`` or ``:`` — those have dedicated sub-sections.
* ``afterComma``             — single space after ``,``.
* ``beforeSemicolon``        — allow a space before ``;`` (default off).
* ``assignment.spaceBefore`` — space before ``:=`` (e.g. ``x := 1``).
* ``assignment.spaceAfter``  — space after ``:=``.
* ``declarationColon.spaceBefore`` — space before ``:`` in declarations
  (e.g. ``num : Integer``).
* ``declarationColon.spaceAfter``  — space after ``:`` in declarations
  (e.g. ``num: Integer``). Note that when ``alignment.alignVarColons`` is
  on, the alignment pass overrides the *before* spacing to pad to the
  aligned column and normalises the *after* spacing to one space.
"""

from __future__ import annotations

from typing import Any

from ..tokenizer import NEWLINE, OPERATOR, WHITESPACE, Token


# Binary operators covered by the master ``aroundOperators`` toggle.
# ``:=`` and ``:`` are NOT in this set — they have their own config.
_BINARY_OPS = {"=", "<>", "<=", ">=", "+=", "-=", "*=", "/="}


def _ensure_space_before(tokens: list[Token], idx: int, want: bool) -> int:
    """Make ``tokens[idx]`` have / not have a single-space prefix.

    Returns the possibly-shifted index of the original token.
    Leading whitespace at the start of a physical line is left alone —
    we never try to re-indent here (that's the alignment / indentation
    pass's job).
    """
    if idx <= 0:
        return idx
    prev = tokens[idx - 1]
    if prev.type == NEWLINE:
        return idx  # at line start — leave leading indentation alone
    if want:
        if prev.type != WHITESPACE:
            tokens.insert(
                idx,
                Token(WHITESPACE, " ", tokens[idx].line, tokens[idx].col),
            )
            return idx + 1
        if prev.value != " ":
            prev.value = " "
        return idx
    # want == False
    if prev.type == WHITESPACE:
        del tokens[idx - 1]
        return idx - 1
    return idx


def _ensure_space_after(tokens: list[Token], idx: int, want: bool) -> None:
    if idx + 1 >= len(tokens):
        return
    nxt = tokens[idx + 1]
    if nxt.type == NEWLINE:
        return
    if want:
        if nxt.type != WHITESPACE:
            tokens.insert(
                idx + 1,
                Token(WHITESPACE, " ", tokens[idx].line, tokens[idx].col),
            )
        elif nxt.value != " ":
            nxt.value = " "
        return
    # want == False
    if nxt.type == WHITESPACE:
        del tokens[idx + 1]


def apply(tokens: list[Token], config: dict[str, Any]) -> None:
    sp = config.get("spacing", {}) or {}
    do_ops = bool(sp.get("aroundOperators", True))
    do_comma = bool(sp.get("afterComma", True))
    no_space_before_semi = not bool(sp.get("beforeSemicolon", False))

    assign = sp.get("assignment", {}) or {}
    assign_before = bool(assign.get("spaceBefore", True))
    assign_after = bool(assign.get("spaceAfter", True))

    decl_colon = sp.get("declarationColon", {}) or {}
    colon_before = bool(decl_colon.get("spaceBefore", False))
    colon_after = bool(decl_colon.get("spaceAfter", True))

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok.type == OPERATOR and tok.value == ":=":
            i = _ensure_space_before(tokens, i, assign_before)
            _ensure_space_after(tokens, i, assign_after)

        elif tok.type == OPERATOR and tok.value == ":":
            i = _ensure_space_before(tokens, i, colon_before)
            _ensure_space_after(tokens, i, colon_after)

        elif do_ops and tok.type == OPERATOR and tok.value in _BINARY_OPS:
            i = _ensure_space_before(tokens, i, True)
            _ensure_space_after(tokens, i, True)

        elif do_comma and tok.type == OPERATOR and tok.value == ",":
            _ensure_space_after(tokens, i, True)

        elif no_space_before_semi and tok.type == OPERATOR and tok.value == ";":
            i = _ensure_space_before(tokens, i, False)

        i += 1

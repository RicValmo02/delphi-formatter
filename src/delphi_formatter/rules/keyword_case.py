"""Normalise the case of Delphi keywords and built-in type names.

Operates directly on the token stream (in place). Directives are also
normalised as keywords since many Delphi color schemes treat them the same.
"""

from __future__ import annotations

from typing import Any

from ..tokenizer import KEYWORD, IDENT, Token
from ..keywords import DIRECTIVES, is_builtin_type


def _apply_case(word: str, mode: str) -> str:
    if mode == "lower":
        return word.lower()
    if mode == "upper":
        return word.upper()
    return word


def apply(tokens: list[Token], config: dict[str, Any]) -> None:
    kw_mode = config.get("keywords", {}).get("case", "preserve")
    bt_mode = config.get("builtinTypes", {}).get("case", "preserve")

    # "match-keywords" means: built-in types follow whatever the user chose
    # for keywords. Resolve here so the rest of the pass never sees the
    # synthetic value.
    if bt_mode == "match-keywords":
        bt_mode = kw_mode

    if kw_mode == "preserve" and bt_mode == "preserve":
        return

    for tok in tokens:
        if tok.type == KEYWORD:
            # KEYWORD tokens may carry a leading '&' escape (rare); keep it.
            raw = tok.value[1:] if tok.value.startswith("&") else tok.value
            prefix = "&" if tok.value.startswith("&") else ""
            # Words like `string`, `file` are both keywords *and* built-in types;
            # they should follow the built-in type setting when that's specified.
            if is_builtin_type(raw) and bt_mode != "preserve":
                tok.value = prefix + _apply_case(raw, bt_mode)
            elif kw_mode != "preserve":
                tok.value = prefix + _apply_case(raw, kw_mode)
        elif tok.type == IDENT:
            if bt_mode != "preserve" and is_builtin_type(tok.value):
                tok.value = _apply_case(tok.value, bt_mode)
            elif kw_mode != "preserve" and tok.value.lower() in DIRECTIVES:
                # Contextual keywords (override, virtual, strict, ...). These
                # are *usually* the same thing you'd want styled as keywords.
                tok.value = _apply_case(tok.value, kw_mode)

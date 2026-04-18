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

    # Synthetic mode: 'match-keywords' means "follow whatever the user picked
    # for 'keywords.case'". Resolve it here so the rest of the pass does not
    # need to know about it.
    if bt_mode == "match-keywords":
        bt_mode = kw_mode

    # Per-type overrides (case-insensitive lookup -> literal replacement).
    overrides_raw = config.get("builtinTypes", {}).get("overrides") or {}
    bt_overrides: dict[str, str] = {
        k.lower(): v
        for k, v in overrides_raw.items()
        if isinstance(k, str) and isinstance(v, str)
    }

    # Early-out only if nothing can actually change the output.
    if kw_mode == "preserve" and bt_mode == "preserve" and not bt_overrides:
        return

    def _emit_builtin(raw: str) -> str:
        """Resolve a built-in type token to its final spelling."""
        override = bt_overrides.get(raw.lower())
        if override is not None:
            return override
        if bt_mode == "preserve":
            return raw
        return _apply_case(raw, bt_mode)

    for tok in tokens:
        if tok.type == KEYWORD:
            # KEYWORD tokens may carry a leading '&' escape (rare); keep it.
            raw = tok.value[1:] if tok.value.startswith("&") else tok.value
            prefix = "&" if tok.value.startswith("&") else ""
            # Words like `string`, `file` are both keywords *and* built-in types;
            # they should follow the built-in type setting when that's specified.
            if is_builtin_type(raw):
                tok.value = prefix + _emit_builtin(raw)
            elif kw_mode != "preserve":
                tok.value = prefix + _apply_case(raw, kw_mode)
        elif tok.type == IDENT:
            if is_builtin_type(tok.value) and (
                bt_mode != "preserve" or tok.value.lower() in bt_overrides
            ):
                tok.value = _emit_builtin(tok.value)
            elif kw_mode != "preserve" and tok.value.lower() in DIRECTIVES:
                # Contextual keywords (override, virtual, strict, ...). These
                # are *usually* the same thing you'd want styled as keywords.
                tok.value = _apply_case(tok.value, kw_mode)

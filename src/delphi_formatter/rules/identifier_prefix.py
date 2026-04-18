"""Rename variables / fields according to prefix rules.

Three rule families are implemented:

* ``variablePrefix.local``      prefix for variables declared in a ``var``
                                 section inside a procedure / function body
                                 (e.g. ``ciao`` -> ``LCiao``).
* ``variablePrefix.classField`` prefix for fields declared inside a
                                 ``class`` / ``record`` block
                                 (e.g. ``data`` -> ``FData``).
* ``variablePrefix.byType``     type-based prefix, e.g. any variable of
                                 type ``TButton`` gets ``btn`` prepended.

The pass identifies declarations, computes a rename map, and then applies
it to every identifier token that matches (skipping tokens that follow a
``.`` — those are member accesses, not the variable itself).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..tokenizer import (
    COMMENT,
    DIRECTIVE,
    EOF,
    IDENT,
    KEYWORD,
    NEWLINE,
    OPERATOR,
    WHITESPACE,
    Token,
)
from ..keywords import TYPE_LIKE, is_keyword_or_directive


# ---------------------------------------------------------------------------
# Helpers for walking only the "significant" tokens.
# ---------------------------------------------------------------------------

_TRIVIA = {WHITESPACE, NEWLINE, COMMENT, DIRECTIVE, EOF}


def _significant(tokens: list[Token]) -> list[tuple[int, Token]]:
    return [(i, t) for i, t in enumerate(tokens) if t.type not in _TRIVIA]


def _lv(tok: Token) -> str:
    return tok.value.lower()


# Opening keywords that pair with `end` inside a procedure body.
_BLOCK_OPENERS = {"begin", "case", "try", "asm", "record", "class", "object"}


# ---------------------------------------------------------------------------
# Scope detection
# ---------------------------------------------------------------------------


@dataclass
class ProcScope:
    """A procedure/function body. Indices are into ``sig`` (significant list)."""
    header_start: int   # index of the `procedure` / `function` keyword
    begin_idx: int      # index of the `begin` keyword
    body_end: int       # index of the matching `end` keyword


@dataclass
class ClassScope:
    """A class / record type block."""
    keyword_idx: int   # index of the `class` or `record` keyword
    end_idx: int       # index of the matching `end`


def _find_scopes(sig: list[tuple[int, Token]]) -> tuple[list[ClassScope], list[ProcScope]]:
    class_scopes: list[ClassScope] = []
    proc_scopes: list[ProcScope] = []

    n = len(sig)
    i = 0
    while i < n:
        _, tok = sig[i]
        lv = _lv(tok)

        # --- type definition: `... = class ...` or `... = record ...`
        if tok.type == KEYWORD and lv in ("class", "record"):
            # Must be preceded (significantly) by `=` to count as a type def.
            prev_val = sig[i - 1][1].value if i > 0 else ""
            if prev_val == "=":
                # Forward declaration? `TFoo = class;` — skip.
                if i + 1 < n and sig[i + 1][1].value == ";":
                    i += 1
                    continue
                # class helper / class of / class function — skip "class" usage
                # inside declarations that aren't actual type bodies.
                if lv == "class" and i + 1 < n and _lv(sig[i + 1][1]) in (
                    "of", "helper", "function", "procedure", "property",
                    "constructor", "destructor", "var",
                ):
                    i += 1
                    continue
                end_idx = _match_class_end(sig, i)
                if end_idx > i:
                    class_scopes.append(ClassScope(keyword_idx=i, end_idx=end_idx))
                    i = end_idx + 1
                    continue

        # --- procedure / function / constructor / destructor with a body
        if tok.type == KEYWORD and lv in (
            "procedure", "function", "constructor", "destructor"
        ):
            body = _find_proc_body(sig, i)
            if body is not None:
                proc_scopes.append(body)
                i = body.body_end + 1
                continue

        i += 1

    return class_scopes, proc_scopes


def _match_class_end(sig: list[tuple[int, Token]], start: int) -> int:
    """Given the index of a ``class``/``record`` keyword starting a type block,
    return the index of the matching ``end`` keyword. Returns -1 on failure.
    """
    depth = 1
    j = start + 1
    n = len(sig)
    while j < n:
        v = _lv(sig[j][1])
        raw = sig[j][1].value
        if v == "end":
            depth -= 1
            if depth == 0:
                return j
        elif v in ("record", "class") and sig[j - 1][1].value == "=":
            # nested inline type def (rare)
            depth += 1
        elif v == "case":
            # variant record: `case X of` — pairs with end at this depth
            depth += 1
        j += 1
    return -1


def _find_proc_body(sig: list[tuple[int, Token]], header_start: int) -> ProcScope | None:
    """Locate the body of a procedure/function starting at *header_start*.

    Returns None for forward/interface declarations (no body).
    """
    n = len(sig)
    # Scan forward past signature: skip parens, look for a terminating ';' then
    # keep going through declaration sections (var/const/type/label) until
    # we hit `begin`. If we hit another `procedure`/`function`/`implementation`
    # without finding a `begin`, this is a header-only declaration.
    paren_depth = 0
    j = header_start + 1
    begin_idx = -1
    while j < n:
        v = _lv(sig[j][1])
        raw = sig[j][1].value
        if raw == "(":
            paren_depth += 1
        elif raw == ")":
            paren_depth -= 1
        elif paren_depth == 0:
            if v == "begin":
                begin_idx = j
                break
            if v in ("end",):
                return None  # unexpected — bail
            if v in ("procedure", "function", "constructor", "destructor") and j > header_start:
                # ensure we're not inside a parameter list (we aren't, paren_depth==0)
                # ensure previous token wasn't `=` (method var/type ref) — heuristic
                prev = sig[j - 1][1].value.lower() if j > 0 else ""
                if prev not in ("=", ":"):
                    return None
            if v in ("implementation", "interface", "initialization", "finalization"):
                return None
        j += 1

    if begin_idx < 0:
        return None

    # Find matching `end`
    depth = 1
    k = begin_idx + 1
    while k < n and depth > 0:
        v = _lv(sig[k][1])
        if v in _BLOCK_OPENERS:
            # `case` inside a record-of variant needs pairing; treat uniformly.
            depth += 1
        elif v == "end":
            depth -= 1
            if depth == 0:
                return ProcScope(header_start, begin_idx, k)
        k += 1
    return None


# ---------------------------------------------------------------------------
# Declaration parsing
# ---------------------------------------------------------------------------


@dataclass
class Decl:
    name_token_idx: int      # index into the full token list
    name: str
    type_name: str | None
    scope: str               # 'local' | 'field'


def _parse_var_block(
    sig: list[tuple[int, Token]], start: int, end: int, scope: str
) -> list[Decl]:
    """Parse a ``var`` block covering sig[start:end] and return Decl list.

    Grammar recognised: ``IDENT (, IDENT)* : TYPE_REF [ = DEFAULT ] ;`` possibly
    repeated. Anything unrecognised causes that declaration to be skipped — we
    never want to crash on valid-but-unusual Delphi.
    """
    decls: list[Decl] = []
    i = start
    while i < end:
        tok_idx, tok = sig[i]
        # Skip separators / section terminators
        if tok.value == ";":
            i += 1
            continue
        if tok.type != IDENT:
            i += 1
            continue

        # Collect identifier list
        names: list[tuple[int, str]] = []
        names.append((tok_idx, tok.value))
        j = i + 1
        while j < end and sig[j][1].value == "," and j + 1 < end and sig[j + 1][1].type == IDENT:
            nt_idx, nt = sig[j + 1]
            names.append((nt_idx, nt.value))
            j += 2

        if j >= end or sig[j][1].value != ":":
            # Not a declaration pattern; skip.
            i = j + 1
            continue

        j += 1  # skip ':'
        # Collect type name: first IDENT after ':' (ignoring array/record/..)
        type_name: str | None = None
        if j < end:
            ttok = sig[j][1]
            if ttok.type == IDENT:
                type_name = ttok.value
            elif ttok.type == KEYWORD and _lv(ttok) in (
                "string", "array", "set", "record", "class", "file", "procedure", "function",
            ):
                type_name = ttok.value

        # Skip to end of declaration (next ';' at paren depth 0 within [j:end])
        paren_depth = 0
        k = j
        while k < end:
            raw = sig[k][1].value
            if raw == "(":
                paren_depth += 1
            elif raw == ")":
                paren_depth -= 1
            elif raw == ";" and paren_depth == 0:
                break
            k += 1

        for n_idx, n_val in names:
            decls.append(Decl(n_idx, n_val, type_name, scope))

        i = k + 1

    return decls


def _collect_local_decls(
    sig: list[tuple[int, Token]], proc: ProcScope
) -> list[Decl]:
    """Scan proc header-area for ``var`` sections and return locals."""
    decls: list[Decl] = []
    i = proc.header_start + 1
    while i < proc.begin_idx:
        tok = sig[i][1]
        lv = _lv(tok)
        if tok.type == KEYWORD and lv == "var":
            # var block runs until next section keyword or `begin`
            j = i + 1
            while j < proc.begin_idx:
                v = _lv(sig[j][1])
                if v in ("begin", "const", "var", "type", "label", "resourcestring",
                         "procedure", "function", "constructor", "destructor"):
                    break
                j += 1
            decls.extend(_parse_var_block(sig, i + 1, j, scope="local"))
            i = j
            continue
        i += 1
    return decls


def _collect_class_fields(
    sig: list[tuple[int, Token]], cls: ClassScope
) -> list[Decl]:
    """Scan a class/record block for field declarations."""
    decls: list[Decl] = []
    i = cls.keyword_idx + 1
    # Skip optional inheritance `(TBase)` or `(TBase, IFoo)`
    if i < cls.end_idx and sig[i][1].value == "(":
        depth = 1
        i += 1
        while i < cls.end_idx and depth > 0:
            v = sig[i][1].value
            if v == "(":
                depth += 1
            elif v == ")":
                depth -= 1
            i += 1

    # Walk members. Skip method declarations entirely; collect field decls.
    while i < cls.end_idx:
        tok = sig[i][1]
        lv = _lv(tok)
        raw = tok.value

        if tok.type == KEYWORD and lv in (
            "procedure", "function", "constructor", "destructor", "property",
            "class",   # e.g. 'class function Foo...'
        ):
            # Skip to the ';' that ends this declaration
            paren_depth = 0
            j = i + 1
            while j < cls.end_idx:
                v = sig[j][1].value
                lv2 = _lv(sig[j][1])
                if v == "(":
                    paren_depth += 1
                elif v == ")":
                    paren_depth -= 1
                elif v == ";" and paren_depth == 0:
                    break
                j += 1
            # Swallow trailing directives: `; overload; virtual; stdcall;`
            j += 1
            while j < cls.end_idx:
                v = _lv(sig[j][1])
                if is_keyword_or_directive(v) and v in (
                    "overload", "override", "virtual", "dynamic", "abstract",
                    "reintroduce", "stdcall", "cdecl", "pascal", "register",
                    "safecall", "platform", "deprecated", "inline", "static",
                    "message", "default", "forward",
                ):
                    # skip directive and optional ';'
                    j += 1
                    if j < cls.end_idx and sig[j][1].value == ";":
                        j += 1
                    continue
                break
            i = j
            continue

        if lv in (
            "private", "protected", "public", "published", "strict", "automated",
        ):
            i += 1
            continue

        if raw == ";":
            i += 1
            continue

        if tok.type == IDENT:
            # Try to parse as a field declaration
            names: list[tuple[int, str]] = [(sig[i][0], tok.value)]
            j = i + 1
            while j < cls.end_idx and sig[j][1].value == "," and j + 1 < cls.end_idx and sig[j + 1][1].type == IDENT:
                names.append((sig[j + 1][0], sig[j + 1][1].value))
                j += 2

            if j >= cls.end_idx or sig[j][1].value != ":":
                i = j + 1
                continue

            j += 1  # skip ':'
            type_name: str | None = None
            if j < cls.end_idx:
                ttok = sig[j][1]
                if ttok.type in (IDENT, KEYWORD):
                    type_name = ttok.value

            # Advance past decl (to ';' at paren depth 0)
            paren_depth = 0
            k = j
            while k < cls.end_idx:
                v = sig[k][1].value
                if v == "(":
                    paren_depth += 1
                elif v == ")":
                    paren_depth -= 1
                elif v == ";" and paren_depth == 0:
                    break
                k += 1

            for n_idx, n_val in names:
                decls.append(Decl(n_idx, n_val, type_name, scope="field"))

            i = k + 1
            continue

        i += 1

    return decls


# ---------------------------------------------------------------------------
# Rename computation
# ---------------------------------------------------------------------------


def _match_type_rule(type_name: str, rules: list[dict[str, Any]]) -> str | None:
    for rule in rules:
        pat = rule.get("typePattern", "")
        prefix = rule.get("prefix", "")
        if not pat:
            continue
        try:
            if re.fullmatch(pat, type_name, re.IGNORECASE):
                return prefix
        except re.error:
            if pat.lower() == type_name.lower():
                return prefix
    return None


def _compute_new_name(decl: Decl, config: dict[str, Any]) -> str | None:
    vp = config.get("variablePrefix", {})
    by_type_cfg = vp.get("byType", {}) or {}
    local_cfg = vp.get("local", {}) or {}
    field_cfg = vp.get("classField", {}) or {}

    type_prefix: str | None = None
    if by_type_cfg.get("enabled") and decl.type_name:
        type_prefix = _match_type_rule(decl.type_name, by_type_cfg.get("rules", []) or [])

    scope_prefix: str | None = None
    scope_capitalize = True
    if decl.scope == "local" and local_cfg.get("enabled"):
        scope_prefix = local_cfg.get("prefix", "") or None
        scope_capitalize = bool(local_cfg.get("capitalizeAfterPrefix", True))
    elif decl.scope == "field" and field_cfg.get("enabled"):
        scope_prefix = field_cfg.get("prefix", "") or None
        scope_capitalize = bool(field_cfg.get("capitalizeAfterPrefix", True))

    conflict = by_type_cfg.get("conflictResolution", "typePrefixOverridesScope")
    if type_prefix is not None and scope_prefix is not None:
        if conflict == "typePrefixOverridesScope":
            use_prefix, use_cap = type_prefix, True
        else:  # scopePrefixOverridesType
            use_prefix, use_cap = scope_prefix, scope_capitalize
    elif type_prefix is not None:
        use_prefix, use_cap = type_prefix, True
    elif scope_prefix is not None:
        use_prefix, use_cap = scope_prefix, scope_capitalize
    else:
        return None

    old = decl.name
    if not use_prefix:
        return None

    # Already prefixed?
    if old.lower().startswith(use_prefix.lower()):
        remainder = old[len(use_prefix):]
        if remainder and (remainder[0].isupper() or not use_cap or not remainder[0].isalpha()):
            return None

    rest = old
    if use_cap and rest:
        rest = rest[0].upper() + rest[1:]
    return use_prefix + rest


# ---------------------------------------------------------------------------
# Rename application
# ---------------------------------------------------------------------------


def _apply_rename(
    tokens: list[Token],
    rename_map: dict[str, str],
    token_range: tuple[int, int] | None,
) -> None:
    """Rewrite identifiers matching *rename_map* (case-insensitive) in place.

    If ``token_range`` is given, only tokens in that [start, end] range are
    rewritten. Tokens immediately following ``.`` (member access) are skipped.
    """
    if not rename_map:
        return
    start, end = (0, len(tokens) - 1) if token_range is None else token_range
    # Pre-normalise map keys
    norm = {k.lower(): v for k, v in rename_map.items()}

    # Track "last non-trivia token" to detect `.` prefix for member access.
    last_nontrivia: Token | None = None
    for i in range(0, start):
        t = tokens[i]
        if t.type not in _TRIVIA:
            last_nontrivia = t

    for i in range(start, end + 1):
        tok = tokens[i]
        if tok.type in _TRIVIA:
            continue
        if tok.type == IDENT:
            key = tok.value.lower()
            if key in norm:
                # Skip member accesses: previous significant token is `.`
                if last_nontrivia is not None and last_nontrivia.value == ".":
                    pass
                else:
                    tok.value = norm[key]
        last_nontrivia = tok


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply(tokens: list[Token], config: dict[str, Any]) -> None:
    vp = config.get("variablePrefix", {}) or {}
    if not (
        (vp.get("local", {}) or {}).get("enabled")
        or (vp.get("classField", {}) or {}).get("enabled")
        or (vp.get("byType", {}) or {}).get("enabled")
    ):
        return

    sig = _significant(tokens)
    if not sig:
        return

    class_scopes, proc_scopes = _find_scopes(sig)

    # --- Collect declarations
    field_decls: list[Decl] = []
    for cls in class_scopes:
        field_decls.extend(_collect_class_fields(sig, cls))

    # Map (proc_index) -> list of decls
    proc_decls: list[tuple[ProcScope, list[Decl]]] = []
    for proc in proc_scopes:
        proc_decls.append((proc, _collect_local_decls(sig, proc)))

    # --- Compute rename maps
    # Class fields are renamed unit-wide (referenced from methods elsewhere).
    field_map: dict[str, str] = {}
    for d in field_decls:
        new = _compute_new_name(d, config)
        if new and new.lower() != d.name.lower():
            field_map[d.name] = new

    # Locals are renamed only within their procedure's body + var section.
    _apply_rename(tokens, field_map, token_range=None)

    for proc, decls in proc_decls:
        local_map: dict[str, str] = {}
        for d in decls:
            new = _compute_new_name(d, config)
            if new and new.lower() != d.name.lower():
                local_map[d.name] = new
        if local_map:
            start_tok_idx = sig[proc.header_start][0]
            end_tok_idx = sig[proc.body_end][0]
            _apply_rename(tokens, local_map, token_range=(start_tok_idx, end_tok_idx))

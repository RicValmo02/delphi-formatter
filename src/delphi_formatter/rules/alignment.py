"""Column alignment for ``var`` and ``const`` sections.

Text-level pass (runs on final source string) that:

* aligns ``:`` in consecutive ``var`` declarations within a block
* aligns ``=`` in consecutive ``const`` declarations within a block

The heuristic looks for groups of adjacent declaration lines. A group is
broken by a blank line, a comment line, or a line that doesn't look like
``IDENT [, IDENT]* : TYPE`` / ``IDENT = VALUE``.

Strings, comments and the ``:=`` operator are respected (we never align on
a ``:`` that is part of ``:=``).
"""

from __future__ import annotations

import re
from typing import Any


_VAR_DECL_RE = re.compile(
    r"""^(?P<indent>\s*)(?P<names>[A-Za-z_][A-Za-z_0-9]*(?:\s*,\s*[A-Za-z_][A-Za-z_0-9]*)*)\s*
        (?P<colon>:)(?!=)(?P<rest>.*)$""",
    re.VERBOSE,
)

_CONST_DECL_RE = re.compile(
    r"^(?P<indent>\s*)(?P<name>[A-Za-z_][A-Za-z_0-9]*)\s*(?P<eq>=)\s*(?P<rest>.*)$"
)


def _is_comment_line(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("//") or stripped.startswith("{") or stripped.startswith("(*")


def _align_var_group(lines: list[str], max_spaces: int) -> list[str]:
    parsed = []
    for ln in lines:
        m = _VAR_DECL_RE.match(ln)
        if not m:
            return lines  # abort alignment for this group
        parsed.append(m)

    # Compute desired column (in characters) for the colon
    target = 0
    for m in parsed:
        left = m.group("indent") + m.group("names")
        target = max(target, len(left.rstrip()) + 1)  # +1 for a space before ':'
    if target <= 0:
        return lines
    target = min(target, max_spaces + 1)

    out = []
    for m in parsed:
        left = (m.group("indent") + m.group("names")).rstrip()
        pad = " " * max(1, target - len(left))
        rest = m.group("rest")
        # Normalise to exactly one space after the colon for readability.
        if rest and not rest.startswith(" "):
            rest = " " + rest.lstrip()
        elif rest.startswith("  "):
            rest = " " + rest.lstrip()
        out.append(f"{left}{pad}:{rest}")
    return out


def _align_const_group(lines: list[str], max_spaces: int) -> list[str]:
    parsed = []
    for ln in lines:
        m = _CONST_DECL_RE.match(ln)
        if not m:
            return lines
        parsed.append(m)

    target = 0
    for m in parsed:
        left = m.group("indent") + m.group("name")
        target = max(target, len(left.rstrip()) + 1)
    target = min(target, max_spaces + 1)

    out = []
    for m in parsed:
        left = (m.group("indent") + m.group("name")).rstrip()
        pad = " " * max(1, target - len(left))
        rest = m.group("rest")
        if rest and not rest.startswith(" "):
            rest = " " + rest.lstrip()
        out.append(f"{left}{pad}={rest}")
    return out


def apply(source: str, config: dict[str, Any]) -> str:
    al = config.get("alignment", {}) or {}
    do_var = bool(al.get("alignVarColons", False))
    do_const = bool(al.get("alignConstEquals", False))
    max_spaces = int(al.get("maxAlignSpaces", 40))
    if not do_var and not do_const:
        return source

    lines = source.splitlines(keepends=False)
    keepends_marker = "\n" if source.endswith("\n") else ""

    result: list[str] = []
    i = 0
    n = len(lines)
    current_section: str | None = None  # 'var' | 'const' | None

    while i < n:
        line = lines[i]
        stripped = line.strip().lower()

        # Section keywords on their own line switch context
        if stripped == "var":
            current_section = "var"
            result.append(line)
            i += 1
            continue
        if stripped == "const":
            current_section = "const"
            result.append(line)
            i += 1
            continue
        # Any other section keyword resets
        if stripped in (
            "begin", "implementation", "interface", "type", "uses",
            "initialization", "finalization", "resourcestring", "label",
            "threadvar",
        ):
            current_section = None
            result.append(line)
            i += 1
            continue
        if stripped == "":
            current_section = None
            result.append(line)
            i += 1
            continue
        if _is_comment_line(line):
            # Don't break section, but don't align comment lines
            result.append(line)
            i += 1
            continue

        # Collect a run of matching declaration lines
        if current_section == "var" and do_var and _VAR_DECL_RE.match(line):
            group = [line]
            j = i + 1
            while j < n:
                nxt = lines[j]
                nxt_stripped = nxt.strip()
                if nxt_stripped == "" or _is_comment_line(nxt):
                    break
                if not _VAR_DECL_RE.match(nxt):
                    break
                group.append(nxt)
                j += 1
            result.extend(_align_var_group(group, max_spaces))
            i = j
            continue

        if current_section == "const" and do_const and _CONST_DECL_RE.match(line):
            group = [line]
            j = i + 1
            while j < n:
                nxt = lines[j]
                nxt_stripped = nxt.strip()
                if nxt_stripped == "" or _is_comment_line(nxt):
                    break
                if not _CONST_DECL_RE.match(nxt):
                    break
                group.append(nxt)
                j += 1
            result.extend(_align_const_group(group, max_spaces))
            i = j
            continue

        result.append(line)
        i += 1

    out = "\n".join(result)
    if source.endswith("\n") and not out.endswith("\n"):
        out += "\n"
    return out

"""Text-level whitespace normalisation.

This pass runs AFTER tokens have been re-emitted to a single string. It
handles:

* trailing whitespace on each line
* final newline at EOF
* collapsing consecutive blank lines to a configured maximum
* line-ending normalisation (lf / crlf / auto)
"""

from __future__ import annotations

from typing import Any


def _detect_line_ending(source: str) -> str:
    # If the file has any CRLF, preserve that style by default.
    if "\r\n" in source:
        return "\r\n"
    return "\n"


def apply(source: str, config: dict[str, Any]) -> str:
    eof_cfg = config.get("endOfFile", {}) or {}
    blank_cfg = config.get("blankLines", {}) or {}

    trim_trailing = bool(eof_cfg.get("trimTrailingWhitespace", True))
    ensure_newline = bool(eof_cfg.get("ensureFinalNewline", True))
    line_ending = eof_cfg.get("lineEnding", "auto")

    if line_ending == "auto":
        eol = _detect_line_ending(source)
    elif line_ending == "crlf":
        eol = "\r\n"
    else:
        eol = "\n"

    # Normalise to \n internally, split.
    norm = source.replace("\r\n", "\n").replace("\r", "\n")
    lines = norm.split("\n")

    if trim_trailing:
        lines = [ln.rstrip(" \t") for ln in lines]

    collapse = bool(blank_cfg.get("collapseConsecutive", True))
    max_blank = int(blank_cfg.get("maxConsecutive", 1))
    if collapse and max_blank >= 0:
        collapsed: list[str] = []
        blank_run = 0
        for ln in lines:
            if ln.strip() == "":
                blank_run += 1
                if blank_run <= max_blank:
                    collapsed.append(ln)
            else:
                blank_run = 0
                collapsed.append(ln)
        lines = collapsed

    result = eol.join(lines)
    if ensure_newline and not result.endswith(eol):
        result += eol

    return result

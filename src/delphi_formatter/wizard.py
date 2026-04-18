"""Interactive wizard for building a ``delphi-formatter`` JSON config.

The wizard is a plain stdin/stdout REPL that walks the user through every
option exposed by :mod:`delphi_formatter.config`. It starts from a *profile*
(Minimal, Delphi-standard, VCL Hungarian, or an existing file) and then lets
the user refine any section interactively, including a dedicated sub-loop for
``variablePrefix.byType`` rules where the user enters type-pattern -> prefix
key/value pairs.

All I/O goes through two streams (``stdin`` / ``stdout``) injected into
:func:`run_wizard`, so the whole flow is end-to-end testable by feeding a
scripted ``io.StringIO`` as input.
"""

from __future__ import annotations

import copy
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, TextIO

from .config import default_config, save_config, validate_config
from .formatter import format_source


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


def _profile_minimal() -> dict[str, Any]:
    """Everything off: pure default (keywords lower, all prefixes disabled)."""
    return default_config()


def _profile_delphi_standard() -> dict[str, Any]:
    """Classic Delphi: lower-case keywords + built-in types, ``F`` class fields."""
    cfg = default_config()
    cfg["keywords"]["case"] = "lower"
    cfg["builtinTypes"]["case"] = "match-keywords"
    cfg["variablePrefix"]["classField"]["enabled"] = True
    cfg["variablePrefix"]["classField"]["prefix"] = "F"
    return cfg


def _profile_vcl_hungarian() -> dict[str, Any]:
    """VCL Hungarian: L locals, F fields, byType enabled with common presets."""
    cfg = default_config()
    cfg["keywords"]["case"] = "lower"
    cfg["builtinTypes"]["case"] = "match-keywords"
    cfg["variablePrefix"]["local"]["enabled"] = True
    cfg["variablePrefix"]["local"]["prefix"] = "L"
    cfg["variablePrefix"]["classField"]["enabled"] = True
    cfg["variablePrefix"]["classField"]["prefix"] = "F"
    cfg["variablePrefix"]["byType"]["enabled"] = True
    return cfg


PROFILES: list[tuple[str, str, Callable[[], dict[str, Any]]]] = [
    ("Minimal", "All features disabled (pure defaults).", _profile_minimal),
    (
        "Delphi-standard",
        "Lower-case keywords, 'F' class-field prefix, no type-based rules.",
        _profile_delphi_standard,
    ),
    (
        "VCL Hungarian",
        "Lower-case keywords, 'L' locals, 'F' fields, byType enabled "
        "(btn/edt/lbl/...).",
        _profile_vcl_hungarian,
    ),
]


PREVIEW_SNIPPET = """\
UNIT MyUnit;

INTERFACE

TYPE
  TDemo = CLASS
  PRIVATE
    counter: Integer;
    caption: STRING;
  PUBLIC
    PROCEDURE DoIt;
  END;

IMPLEMENTATION

PROCEDURE TDemo.DoIt;
VAR
  index: Integer;
  message: STRING;
  mainButton: TButton;
BEGIN
  index:=0;
  message:='start';
  mainButton.Caption:=message;
  counter:=counter+1;
END;

END.
"""


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


class _IO:
    """Small wrapper so every prompt routes through the injected streams."""

    def __init__(self, stdin: TextIO, stdout: TextIO) -> None:
        self.stdin = stdin
        self.stdout = stdout

    def write(self, text: str) -> None:
        self.stdout.write(text)
        self.stdout.flush()

    def writeln(self, text: str = "") -> None:
        self.write(text + "\n")

    def readline(self) -> str:
        line = self.stdin.readline()
        # An empty string from readline() means EOF. Treat as blank input so
        # the caller's default applies instead of looping forever.
        if line == "":
            return ""
        return line.rstrip("\r\n")


def _ask_string(io_: _IO, prompt: str, default: str | None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        io_.write(f"{prompt}{suffix}: ")
        answer = io_.readline().strip()
        if answer == "" and default is not None:
            return default
        if answer != "":
            return answer
        io_.writeln("  (empty — please type a value)")


def _ask_yes_no(io_: _IO, prompt: str, default: bool) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        io_.write(f"{prompt} [{hint}]: ")
        answer = io_.readline().strip().lower()
        if answer == "":
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        io_.writeln("  (please answer y or n)")


def _ask_int(io_: _IO, prompt: str, default: int, minimum: int = 0) -> int:
    while True:
        io_.write(f"{prompt} [{default}]: ")
        answer = io_.readline().strip()
        if answer == "":
            return default
        try:
            value = int(answer)
        except ValueError:
            io_.writeln(f"  (not an integer: {answer!r})")
            continue
        if value < minimum:
            io_.writeln(f"  (must be >= {minimum})")
            continue
        return value


def _ask_choice(
    io_: _IO, prompt: str, options: list[str], default: str
) -> str:
    """Ask for one of *options*. Accepts index or literal value."""
    assert default in options, f"default {default!r} not in options {options}"
    io_.writeln(prompt)
    for i, opt in enumerate(options, 1):
        marker = " (default)" if opt == default else ""
        io_.writeln(f"  {i}) {opt}{marker}")
    while True:
        io_.write("Choice: ")
        answer = io_.readline().strip().lower()
        if answer == "":
            return default
        # numeric?
        if answer.isdigit():
            idx = int(answer)
            if 1 <= idx <= len(options):
                return options[idx - 1]
            io_.writeln(f"  (index out of range 1..{len(options)})")
            continue
        # literal?
        for opt in options:
            if opt.lower() == answer:
                return opt
        io_.writeln("  (not a valid choice)")


_PASCAL_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ask_pascal_ident(io_: _IO, prompt: str, default: str | None) -> str:
    while True:
        value = _ask_string(io_, prompt, default)
        if _PASCAL_IDENT_RE.match(value):
            return value
        io_.writeln(
            f"  {value!r} is not a valid Pascal identifier "
            "(letters, digits and underscore; must not start with a digit)"
        )


def _ask_regex(io_: _IO, prompt: str, default: str | None) -> str:
    while True:
        value = _ask_string(io_, prompt, default)
        try:
            re.compile(value)
        except re.error as exc:
            io_.writeln(f"  invalid regex: {exc}")
            continue
        return value


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _section_indent(io_: _IO, cfg: dict[str, Any]) -> None:
    io_.writeln("\n== Indentation ==")
    ind = cfg["indent"]
    ind["style"] = _ask_choice(
        io_, "Indent style:", ["spaces", "tabs"], ind.get("style", "spaces")
    )
    ind["size"] = _ask_int(
        io_, "Indent size", int(ind.get("size", 2)), minimum=1
    )
    ind["continuationIndent"] = _ask_int(
        io_,
        "Continuation indent",
        int(ind.get("continuationIndent", 2)),
        minimum=0,
    )


def _section_cases(io_: _IO, cfg: dict[str, Any]) -> None:
    io_.writeln("\n== Keyword & built-in-type case ==")
    kw_opts = ["lower", "upper", "preserve"]
    cfg["keywords"]["case"] = _ask_choice(
        io_, "Keyword case (begin, end, procedure, var, ...):",
        kw_opts, cfg["keywords"].get("case", "lower"),
    )

    # Built-in types: Integer, String, Boolean, Char, TDateTime, ... . The
    # extra 'match-keywords' option makes them follow whatever was just
    # picked for keywords (handy when you want EVERYTHING lowercase).
    io_.writeln(
        "\nBuilt-in type case (Integer, String, Boolean, Char, TDateTime, ...)."
    )
    io_.writeln(
        "Tip: pick 'match-keywords' to keep built-in types in sync with "
        "the keyword case above."
    )
    bt_opts = ["lower", "upper", "preserve", "match-keywords"]
    current_bt = cfg["builtinTypes"].get("case", "preserve")
    if current_bt not in bt_opts:
        current_bt = "preserve"
    cfg["builtinTypes"]["case"] = _ask_choice(
        io_, "Built-in type case:", bt_opts, current_bt,
    )


def _section_local_prefix(io_: _IO, cfg: dict[str, Any]) -> None:
    io_.writeln("\n== Local variable prefix (var inside procedure/function) ==")
    node = cfg["variablePrefix"]["local"]
    node["enabled"] = _ask_yes_no(
        io_, "Enable local-variable prefixing?", bool(node.get("enabled", False))
    )
    if not node["enabled"]:
        return
    node["prefix"] = _ask_pascal_ident(
        io_, "Prefix (e.g. L so 'ciao' -> 'LCiao')", str(node.get("prefix", "L"))
    )
    node["capitalizeAfterPrefix"] = _ask_yes_no(
        io_,
        "Capitalize first letter after the prefix? "
        f"(on: '{node['prefix']}Ciao', off: '{node['prefix']}ciao')",
        bool(node.get("capitalizeAfterPrefix", True)),
    )


def _section_field_prefix(io_: _IO, cfg: dict[str, Any]) -> None:
    io_.writeln("\n== Class/record field prefix ==")
    node = cfg["variablePrefix"]["classField"]
    node["enabled"] = _ask_yes_no(
        io_, "Enable class-field prefixing?", bool(node.get("enabled", False))
    )
    if not node["enabled"]:
        return
    node["prefix"] = _ask_pascal_ident(
        io_, "Prefix (Delphi convention is 'F')", str(node.get("prefix", "F"))
    )
    node["capitalizeAfterPrefix"] = _ask_yes_no(
        io_,
        "Capitalize first letter after the prefix? "
        f"(on: '{node['prefix']}Counter', off: '{node['prefix']}counter')",
        bool(node.get("capitalizeAfterPrefix", True)),
    )


def _print_byType_rules(io_: _IO, rules: list[dict[str, str]]) -> None:
    if not rules:
        io_.writeln("  (no rules)")
        return
    # Align the '->' column for readability.
    width = max(len(r["typePattern"]) for r in rules)
    for i, r in enumerate(rules, 1):
        pat = r["typePattern"].ljust(width)
        io_.writeln(f"  [{i:>2}] {pat}  ->  {r['prefix']}")


def _section_bytype(io_: _IO, cfg: dict[str, Any]) -> None:
    """Dedicated sub-loop for the user to manage typePattern -> prefix pairs."""

    io_.writeln("\n== Type-based prefix rules (byType) ==")
    node = cfg["variablePrefix"]["byType"]
    node["enabled"] = _ask_yes_no(
        io_,
        "Enable type-based prefixing (e.g. TButton -> btn)?",
        bool(node.get("enabled", False)),
    )
    if not node["enabled"]:
        return

    node["conflictResolution"] = _ask_choice(
        io_,
        "When a variable matches BOTH a scope rule (local/field) AND a byType "
        "rule, which wins?",
        ["typePrefixOverridesScope", "scopePrefixOverridesType"],
        node.get("conflictResolution", "typePrefixOverridesScope"),
    )

    rules: list[dict[str, str]] = list(node.get("rules", []))
    while True:
        io_.writeln(f"\nCurrent rules ({len(rules)}):")
        _print_byType_rules(io_, rules)
        io_.writeln(
            "\nActions:\n"
            "  a) Add rule\n"
            "  r) Remove rule (by number)\n"
            "  e) Edit rule (by number)\n"
            "  c) Clear all rules\n"
            "  d) Done"
        )
        io_.write("> ")
        choice = io_.readline().strip().lower()
        if choice in ("d", "done", ""):
            break
        if choice in ("a", "add"):
            pat = _ask_regex(
                io_, "typePattern (regex, e.g. TButton or TList.*)", None
            )
            pref = _ask_pascal_ident(io_, "prefix (e.g. btn)", None)
            if any(r["typePattern"] == pat for r in rules):
                io_.writeln(
                    f"  note: a rule with pattern {pat!r} already exists "
                    "(keeping both)"
                )
            rules.append({"typePattern": pat, "prefix": pref})
            io_.writeln(f"  added: {pat} -> {pref}")
            continue
        if choice in ("r", "remove"):
            if not rules:
                io_.writeln("  (no rules to remove)")
                continue
            idx = _ask_int(
                io_, "Rule number to remove", 1, minimum=1
            )
            if 1 <= idx <= len(rules):
                removed = rules.pop(idx - 1)
                io_.writeln(
                    f"  removed: {removed['typePattern']} -> {removed['prefix']}"
                )
            else:
                io_.writeln(f"  (out of range 1..{len(rules)})")
            continue
        if choice in ("e", "edit"):
            if not rules:
                io_.writeln("  (no rules to edit)")
                continue
            idx = _ask_int(io_, "Rule number to edit", 1, minimum=1)
            if not (1 <= idx <= len(rules)):
                io_.writeln(f"  (out of range 1..{len(rules)})")
                continue
            current = rules[idx - 1]
            pat = _ask_regex(io_, "typePattern", current["typePattern"])
            pref = _ask_pascal_ident(io_, "prefix", current["prefix"])
            rules[idx - 1] = {"typePattern": pat, "prefix": pref}
            io_.writeln(f"  updated: {pat} -> {pref}")
            continue
        if choice in ("c", "clear"):
            if _ask_yes_no(io_, "Really clear ALL rules?", default=False):
                rules = []
                io_.writeln("  (cleared)")
            continue
        io_.writeln("  (unknown action)")

    node["rules"] = rules


def _section_spacing(io_: _IO, cfg: dict[str, Any]) -> None:
    io_.writeln("\n== Spacing ==")
    sp = cfg["spacing"]

    # --- Assignment operator (:=) ---
    io_.writeln("\n  -- Assignment operator ':=' (e.g. 'num := 5')")
    assign = sp.setdefault("assignment", {"spaceBefore": True, "spaceAfter": True})
    assign["spaceBefore"] = _ask_yes_no(
        io_, "  Space BEFORE ':=' ? (off: 'num:= 5', on: 'num := 5')",
        bool(assign.get("spaceBefore", True)),
    )
    assign["spaceAfter"] = _ask_yes_no(
        io_, "  Space AFTER ':=' ?  (off: 'num :=5', on: 'num := 5')",
        bool(assign.get("spaceAfter", True)),
    )

    # --- Declaration colon (':') ---
    io_.writeln("\n  -- Declaration colon ':' (e.g. 'var num: Integer;')")
    dc = sp.setdefault("declarationColon", {"spaceBefore": False, "spaceAfter": True})
    dc["spaceBefore"] = _ask_yes_no(
        io_, "  Space BEFORE ':' ? (off: 'num: Integer', on: 'num : Integer')",
        bool(dc.get("spaceBefore", False)),
    )
    dc["spaceAfter"] = _ask_yes_no(
        io_, "  Space AFTER ':'  ? (off: 'num:Integer',  on: 'num: Integer')",
        bool(dc.get("spaceAfter", True)),
    )
    if cfg.get("alignment", {}).get("alignVarColons"):
        io_.writeln(
            "  (note: alignVarColons is on - alignment overrides the BEFORE "
            "spacing to reach the aligned column)"
        )

    # --- Other operators ---
    io_.writeln("\n  -- Other binary operators ('=', '<>', '<=', '>=', '+=', ...)")
    sp["aroundOperators"] = _ask_yes_no(
        io_, "  Single space around them? (a=b -> a = b)",
        bool(sp.get("aroundOperators", True)),
    )

    # --- Comma / semicolon / parens ---
    io_.writeln("\n  -- Punctuation")
    sp["afterComma"] = _ask_yes_no(
        io_, "  Single space after ',' (a,b -> a, b)?",
        bool(sp.get("afterComma", True)),
    )
    sp["beforeSemicolon"] = _ask_yes_no(
        io_, "  Space before ';' ?", bool(sp.get("beforeSemicolon", False))
    )
    sp["insideParens"] = _ask_yes_no(
        io_, "  Pad inside parentheses?",
        bool(sp.get("insideParens", False)),
    )


def _section_alignment(io_: _IO, cfg: dict[str, Any]) -> None:
    io_.writeln("\n== Alignment ==")
    al = cfg["alignment"]
    al["alignVarColons"] = _ask_yes_no(
        io_, "Align ':' columns in var blocks?",
        bool(al.get("alignVarColons", True)),
    )
    al["alignConstEquals"] = _ask_yes_no(
        io_, "Align '=' columns in const blocks?",
        bool(al.get("alignConstEquals", True)),
    )
    al["alignAssignments"] = _ask_yes_no(
        io_, "Align ':=' columns in consecutive assignments?",
        bool(al.get("alignAssignments", False)),
    )
    al["maxAlignSpaces"] = _ask_int(
        io_, "Max alignment padding (chars)", int(al.get("maxAlignSpaces", 40)),
        minimum=0,
    )


def _section_blank_lines(io_: _IO, cfg: dict[str, Any]) -> None:
    io_.writeln("\n== Blank lines ==")
    bl = cfg["blankLines"]
    bl["collapseConsecutive"] = _ask_yes_no(
        io_, "Collapse consecutive blank lines?",
        bool(bl.get("collapseConsecutive", True)),
    )
    if bl["collapseConsecutive"]:
        bl["maxConsecutive"] = _ask_int(
            io_, "Max consecutive blank lines", int(bl.get("maxConsecutive", 1)),
            minimum=0,
        )


def _section_end_of_file(io_: _IO, cfg: dict[str, Any]) -> None:
    io_.writeln("\n== End of file / line endings ==")
    eof = cfg["endOfFile"]
    eof["trimTrailingWhitespace"] = _ask_yes_no(
        io_, "Trim trailing whitespace on every line?",
        bool(eof.get("trimTrailingWhitespace", True)),
    )
    eof["ensureFinalNewline"] = _ask_yes_no(
        io_, "Ensure a final newline?",
        bool(eof.get("ensureFinalNewline", True)),
    )
    eof["lineEnding"] = _ask_choice(
        io_, "Line ending:", ["auto", "crlf", "lf"],
        eof.get("lineEnding", "auto"),
    )


def _section_preview(io_: _IO, cfg: dict[str, Any]) -> None:
    io_.writeln("\n== Preview on sample snippet ==")
    io_.writeln("--- input ---")
    io_.write(PREVIEW_SNIPPET)
    if not PREVIEW_SNIPPET.endswith("\n"):
        io_.writeln()
    try:
        formatted = format_source(PREVIEW_SNIPPET, cfg)
    except Exception as exc:  # keep the wizard alive on formatter bugs
        io_.writeln(f"  (preview failed: {exc})")
        return
    io_.writeln("--- formatted with current config ---")
    io_.write(formatted)
    if not formatted.endswith("\n"):
        io_.writeln()


# Data-driven dispatch: label, callable. Order defines the menu.
SECTIONS: list[tuple[str, Callable[[_IO, dict[str, Any]], None]]] = [
    ("Indentation",                        _section_indent),
    ("Keyword & built-in-type case",       _section_cases),
    ("Local variable prefix",              _section_local_prefix),
    ("Class / record field prefix",        _section_field_prefix),
    ("Type-based prefix rules (byType)",   _section_bytype),
    ("Spacing",                            _section_spacing),
    ("Alignment",                          _section_alignment),
    ("Blank lines",                        _section_blank_lines),
    ("End-of-file / line endings",         _section_end_of_file),
    ("Preview on sample",                  _section_preview),
]


# ---------------------------------------------------------------------------
# Top-level wizard
# ---------------------------------------------------------------------------


def _pick_profile(io_: _IO, from_path: Path | None) -> dict[str, Any]:
    """Return the starting config, either from --from or from a PROFILES pick."""
    if from_path is not None:
        io_.writeln(f"Starting from existing config: {from_path}")
        with from_path.open("r", encoding="utf-8") as f:
            user = json.load(f)
        if not isinstance(user, dict):
            raise ValueError(f"Config root must be a JSON object in {from_path}")
        # Deep-merge onto defaults so unset keys inherit.
        from .config import _deep_merge  # local import to avoid cycle at top
        return _deep_merge(default_config(), user)

    io_.writeln("Starting profile:")
    for i, (name, desc, _fn) in enumerate(PROFILES, 1):
        io_.writeln(f"  {i}) {name}  - {desc}")
    while True:
        io_.write(f"Choice [1..{len(PROFILES)}]: ")
        answer = io_.readline().strip()
        if answer == "":
            answer = "1"
        if answer.isdigit():
            idx = int(answer)
            if 1 <= idx <= len(PROFILES):
                name, _desc, fn = PROFILES[idx - 1]
                io_.writeln(f"  -> selected: {name}")
                return fn()
        io_.writeln(f"  (please enter a number 1..{len(PROFILES)})")


def _main_menu(io_: _IO, cfg: dict[str, Any]) -> None:
    """Section menu. Returns when the user picks Save & exit."""
    while True:
        io_.writeln("\nWhich section would you like to configure?")
        for i, (label, _fn) in enumerate(SECTIONS, 1):
            io_.writeln(f"  {i:>2}) {label}")
        save_idx = len(SECTIONS) + 1
        io_.writeln(f"  {save_idx:>2}) Save & exit")
        io_.write("Choice: ")
        answer = io_.readline().strip()
        if answer == "":
            continue
        if not answer.isdigit():
            io_.writeln("  (please enter a number)")
            continue
        idx = int(answer)
        if idx == save_idx:
            return
        if 1 <= idx <= len(SECTIONS):
            _label, fn = SECTIONS[idx - 1]
            fn(io_, cfg)
            continue
        io_.writeln(f"  (out of range 1..{save_idx})")


def run_wizard(
    output_path: Path,
    *,
    force: bool = False,
    from_path: Path | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Entry point. Returns a process exit code."""

    io_ = _IO(stdin or sys.stdin, stdout or sys.stdout)

    io_.writeln("=" * 60)
    io_.writeln("  delphi-formatter - interactive config wizard")
    io_.writeln("=" * 60)
    io_.writeln(
        "This wizard walks you through every option, starting from a\n"
        "profile. At any point you can pick 'Preview on sample' to see the\n"
        "effect of your choices on a small Delphi snippet."
    )

    try:
        cfg = _pick_profile(io_, from_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        io_.writeln(f"\nerror: could not load starting config: {exc}")
        return 2

    if _ask_yes_no(io_, "\nRefine options section by section?", default=True):
        _main_menu(io_, cfg)

    # Validate before writing.
    errors = validate_config(cfg)
    if errors:
        io_.writeln("\nConfig has validation errors, please fix above and retry:")
        for e in errors:
            io_.writeln(f"  - {e}")
        return 2

    if output_path.exists() and not force:
        if not _ask_yes_no(
            io_,
            f"\n{output_path} already exists. Overwrite?",
            default=False,
        ):
            io_.writeln("aborted - nothing written.")
            return 1

    save_config(cfg, output_path)
    io_.writeln(f"\nwrote config to {output_path.resolve()}")
    io_.writeln("you can now run:")
    io_.writeln(
        f"  delphi-formatter format <file.pas> --config {output_path}"
    )
    return 0


# ---------------------------------------------------------------------------
# Convenience: allow ``python -m delphi_formatter.wizard`` for ad-hoc use.
# ---------------------------------------------------------------------------


def _ad_hoc_main() -> int:  # pragma: no cover - manual entry point
    import argparse

    parser = argparse.ArgumentParser(description="Build a delphi-formatter config interactively.")
    parser.add_argument("--output", "-o", default="delphi-formatter.json")
    parser.add_argument("--force", "-f", action="store_true")
    parser.add_argument("--from", dest="from_path", default=None)
    ns = parser.parse_args()
    return run_wizard(
        Path(ns.output),
        force=ns.force,
        from_path=Path(ns.from_path) if ns.from_path else None,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_ad_hoc_main())

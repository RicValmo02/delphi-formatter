"""Command-line interface for delphi-formatter.

Usage
-----

    python -m delphi_formatter format PATH [PATH ...] [--config PATH]
                                     [--write | --diff | --check]
                                     [--include GLOB]... [--exclude GLOB]...
                                     [--quiet | --verbose]
    python -m delphi_formatter check PATH [PATH ...] [--config PATH]
                                    [--include GLOB]... [--exclude GLOB]...
                                    [--quiet | --verbose]
    python -m delphi_formatter init-config [--output delphi-formatter.json]
    python -m delphi_formatter wizard [--output delphi-formatter.json] [--from PATH]

``format`` accepts one or more files or directories. Directories are walked
recursively (see ``--include`` / ``--exclude``). On a single file without
``--write`` / ``--diff`` / ``--check``, the formatted output is printed to
stdout — this is the same behaviour as earlier versions.

On directories (or multiple paths) one of ``--write`` / ``--diff`` / ``--check``
is **required**, so the user never accidentally triggers mass reformatting.

``check`` is a convenience alias for ``format --check``.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from .config import default_config, load_config, save_config, validate_config
from .formatter import format_source
from .runner import (
    DEFAULT_EXCLUDES,
    DEFAULT_INCLUDES,
    Mode,
    Verbosity,
    run,
)
from .wizard import run_wizard


# ---------------------------------------------------------------------------
# Legacy stdin / single-file path (preserved for backward compatibility)
# ---------------------------------------------------------------------------


def _read_source(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _write_output(path: str, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8", newline="")


def _load_and_validate_config(config_arg: str | None) -> tuple[dict | None, int]:
    """Load the user config (or default). Return (config, exit_code_if_error)."""
    config = load_config(config_arg) if config_arg else default_config()
    errors = validate_config(config)
    if errors:
        for e in errors:
            print(f"config error: {e}", file=sys.stderr)
        return None, 2
    return config, 0


def _resolve_verbosity(args: argparse.Namespace) -> Verbosity:
    if getattr(args, "quiet", False):
        return Verbosity.QUIET
    if getattr(args, "verbose", False):
        return Verbosity.VERBOSE
    return Verbosity.NORMAL


def _resolve_excludes(args: argparse.Namespace) -> tuple[str, ...]:
    user = tuple(args.exclude or ())
    if getattr(args, "no_default_excludes", False):
        return user
    return DEFAULT_EXCLUDES + user


def _resolve_includes(args: argparse.Namespace) -> tuple[str, ...]:
    user = tuple(args.include or ())
    return user if user else DEFAULT_INCLUDES


# ---------------------------------------------------------------------------
# Single-file / stdin fast-path (preserves old behavior)
# ---------------------------------------------------------------------------


def _format_stdin_or_single_file(args: argparse.Namespace) -> int:
    """Handle the legacy 'format <file>' and 'format -' cases.

    Used when exactly one path is given and no directory-only flags
    (--check, --include, --exclude) force us through the driver.
    """
    path = args.paths[0]
    source = _read_source(path)
    config, code = _load_and_validate_config(args.config)
    if config is None:
        return code
    formatted = format_source(source, config)

    if args.diff:
        in_lines = source.splitlines(keepends=True)
        out_lines = formatted.splitlines(keepends=True)
        diff = difflib.unified_diff(
            in_lines, out_lines,
            fromfile=path, tofile=f"{path} (formatted)",
        )
        sys.stdout.write("".join(diff))
        return 0

    if args.write:
        if path == "-":
            print("error: --write is incompatible with stdin input", file=sys.stderr)
            return 2
        _write_output(path, formatted)
        print(f"formatted: {path}", file=sys.stderr)
        return 0

    sys.stdout.write(formatted)
    return 0


# ---------------------------------------------------------------------------
# New: directory-aware format / check
# ---------------------------------------------------------------------------


def _resolve_mode(args: argparse.Namespace, *, force_check: bool = False) -> Mode:
    if force_check or getattr(args, "check", False):
        return Mode.CHECK
    if getattr(args, "write", False):
        return Mode.WRITE
    if getattr(args, "diff", False):
        return Mode.DIFF
    return Mode.STDOUT


def _cmd_format(args: argparse.Namespace) -> int:
    paths = args.paths

    # Legacy fast path: single path, stdin ('-'), or a single file without
    # any directory-only flag.
    stdin_only = len(paths) == 1 and paths[0] == "-"
    if stdin_only:
        return _format_stdin_or_single_file(args)

    # Classify paths.
    resolved: list[Path] = []
    for p in paths:
        pp = Path(p)
        if not pp.exists():
            print(f"error: path does not exist: {p}", file=sys.stderr)
            return 2
        resolved.append(pp)

    has_dir = any(p.is_dir() for p in resolved)
    multi = len(resolved) > 1
    mode = _resolve_mode(args)

    # Single file with no mode flag: keep legacy stdout behaviour.
    if not has_dir and not multi and mode is Mode.STDOUT:
        return _format_stdin_or_single_file(args)

    # Directory / multiple paths require an explicit mode.
    if mode is Mode.STDOUT:
        print(
            "error: formatting a directory or multiple paths requires one of "
            "--write, --diff, or --check",
            file=sys.stderr,
        )
        return 2

    config, code = _load_and_validate_config(args.config)
    if config is None:
        return code

    summary = run(
        resolved,
        config,
        mode,
        includes=_resolve_includes(args),
        excludes=_resolve_excludes(args),
        verbosity=_resolve_verbosity(args),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    return summary.exit_code(mode)


def _cmd_check(args: argparse.Namespace) -> int:
    paths = args.paths

    # Backward-compat: a single '-' means read from stdin.
    if len(paths) == 1 and paths[0] == "-":
        source = _read_source("-")
        config, code = _load_and_validate_config(args.config)
        if config is None:
            return code
        formatted = format_source(source, config)
        if formatted != source:
            print("would reformat: <stdin>", file=sys.stderr)
            return 1
        return 0

    resolved: list[Path] = []
    for p in paths:
        pp = Path(p)
        if not pp.exists():
            print(f"error: path does not exist: {p}", file=sys.stderr)
            return 2
        resolved.append(pp)

    config, code = _load_and_validate_config(args.config)
    if config is None:
        return code

    summary = run(
        resolved,
        config,
        Mode.CHECK,
        includes=_resolve_includes(args),
        excludes=_resolve_excludes(args),
        verbosity=_resolve_verbosity(args),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    return summary.exit_code(Mode.CHECK)


def _cmd_init_config(args: argparse.Namespace) -> int:
    output = Path(args.output)
    if output.exists() and not args.force:
        print(
            f"error: {output} already exists (use --force to overwrite)",
            file=sys.stderr,
        )
        return 2
    save_config(default_config(), output)
    print(f"wrote default config to {output}", file=sys.stderr)
    return 0


def _cmd_wizard(args: argparse.Namespace) -> int:
    return run_wizard(
        Path(args.output),
        force=args.force,
        from_path=Path(args.from_path) if args.from_path else None,
    )


# ---------------------------------------------------------------------------
# Parser construction
# ---------------------------------------------------------------------------


def _add_discovery_flags(p: argparse.ArgumentParser) -> None:
    """Shared --include / --exclude / --no-default-excludes / verbosity flags."""
    p.add_argument(
        "--include", action="append", default=None, metavar="GLOB",
        help="Filename glob to include when walking directories "
             "(repeatable; default: *.pas)",
    )
    p.add_argument(
        "--exclude", action="append", default=None, metavar="GLOB",
        help="Path glob to exclude (repeatable, added on top of defaults)",
    )
    p.add_argument(
        "--no-default-excludes", action="store_true",
        help="Disable the built-in excludes (bin/, obj/, __history/, __recovery/)",
    )
    verb = p.add_mutually_exclusive_group()
    verb.add_argument(
        "--quiet", "-q", action="store_true",
        help="Only print the final summary and errors",
    )
    verb.add_argument(
        "--verbose", action="store_true",
        help="Print one line per file, changed or not",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="delphi-formatter",
        description="Configurable formatter for Delphi / Object Pascal source code.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- format ----------------------------------------------------------
    pf = sub.add_parser(
        "format",
        help="Format Delphi source file(s) or directories",
    )
    pf.add_argument(
        "paths", nargs="+",
        help="One or more .pas files or directories; '-' reads from stdin "
             "(only valid as the sole path)",
    )
    pf.add_argument("--config", "-c", help="Path to JSON config file")
    group = pf.add_mutually_exclusive_group()
    group.add_argument(
        "--write", "-w", action="store_true",
        help="Rewrite input files in place",
    )
    group.add_argument(
        "--diff", "-d", action="store_true",
        help="Emit unified diffs on stdout without changing files",
    )
    group.add_argument(
        "--check", action="store_true",
        help="Report what would change; exit 1 if any file is unformatted",
    )
    _add_discovery_flags(pf)
    pf.set_defaults(func=_cmd_format)

    # ---- check -----------------------------------------------------------
    pc = sub.add_parser(
        "check",
        help="Exit 1 if any file under the given path(s) would be reformatted",
    )
    pc.add_argument(
        "paths", nargs="+",
        help="One or more .pas files or directories; '-' reads from stdin "
             "(only valid as the sole path)",
    )
    pc.add_argument("--config", "-c", help="Path to JSON config file")
    _add_discovery_flags(pc)
    pc.set_defaults(func=_cmd_check)

    # ---- init-config -----------------------------------------------------
    pi = sub.add_parser("init-config", help="Write a default config JSON")
    pi.add_argument("--output", "-o", default="delphi-formatter.json", help="Output path")
    pi.add_argument("--force", "-f", action="store_true", help="Overwrite if exists")
    pi.set_defaults(func=_cmd_init_config)

    # ---- wizard ----------------------------------------------------------
    pw = sub.add_parser(
        "wizard",
        help="Build a config JSON interactively (profiles + fine tuning)",
    )
    pw.add_argument(
        "--output", "-o", default="delphi-formatter.json",
        help="Output path (default: delphi-formatter.json)",
    )
    pw.add_argument(
        "--force", "-f", action="store_true",
        help="Overwrite output without asking if it already exists",
    )
    pw.add_argument(
        "--from", dest="from_path", default=None,
        help="Start the wizard from an existing config file instead of a profile",
    )
    pw.set_defaults(func=_cmd_wizard)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)

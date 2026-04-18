"""Command-line interface for delphi-formatter.

Usage
-----

    python -m delphi_formatter format <file.pas> [--config PATH] [--write] [--diff]
    python -m delphi_formatter init-config [--output delphi-formatter.json]
    python -m delphi_formatter check <file.pas> [--config PATH]

``format`` prints to stdout by default (so that it can be piped / diffed /
snapshot-tested). Pass ``--write`` to overwrite the input file in place.
``check`` exits 1 if the file would be reformatted.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from .config import default_config, load_config, save_config, validate_config
from .formatter import format_source


def _read_source(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _write_output(path: str, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8", newline="")


def _cmd_format(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    config = load_config(args.config) if args.config else default_config()
    errors = validate_config(config)
    if errors:
        for e in errors:
            print(f"config error: {e}", file=sys.stderr)
        return 2
    formatted = format_source(source, config)

    if args.diff:
        in_lines = source.splitlines(keepends=True)
        out_lines = formatted.splitlines(keepends=True)
        diff = difflib.unified_diff(
            in_lines, out_lines,
            fromfile=args.file, tofile=f"{args.file} (formatted)",
        )
        sys.stdout.write("".join(diff))
        return 0

    if args.write:
        if args.file == "-":
            print("error: --write is incompatible with stdin input", file=sys.stderr)
            return 2
        _write_output(args.file, formatted)
        print(f"formatted: {args.file}", file=sys.stderr)
        return 0

    sys.stdout.write(formatted)
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    config = load_config(args.config) if args.config else default_config()
    errors = validate_config(config)
    if errors:
        for e in errors:
            print(f"config error: {e}", file=sys.stderr)
        return 2
    formatted = format_source(source, config)
    if formatted != source:
        print(f"would reformat: {args.file}", file=sys.stderr)
        return 1
    return 0


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="delphi-formatter",
        description="Configurable formatter for Delphi / Object Pascal source code.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pf = sub.add_parser("format", help="Format a Delphi source file")
    pf.add_argument("file", help="Path to .pas file, or '-' for stdin")
    pf.add_argument("--config", "-c", help="Path to JSON config file")
    group = pf.add_mutually_exclusive_group()
    group.add_argument("--write", "-w", action="store_true", help="Write result back to file")
    group.add_argument("--diff", "-d", action="store_true", help="Show unified diff instead of output")
    pf.set_defaults(func=_cmd_format)

    pc = sub.add_parser("check", help="Exit 1 if file would be reformatted")
    pc.add_argument("file", help="Path to .pas file, or '-' for stdin")
    pc.add_argument("--config", "-c", help="Path to JSON config file")
    pc.set_defaults(func=_cmd_check)

    pi = sub.add_parser("init-config", help="Write a default config JSON")
    pi.add_argument("--output", "-o", default="delphi-formatter.json", help="Output path")
    pi.add_argument("--force", "-f", action="store_true", help="Overwrite if exists")
    pi.set_defaults(func=_cmd_init_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)

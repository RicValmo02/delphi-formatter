"""Smoke tests for the CLI — argparse plumbing + end-to-end invocations."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from delphi_formatter.cli import build_parser, main


UNFORMATTED_SRC = "BEGIN IF X THEN Y ELSE Z; END;\n"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


class CliParserTests(unittest.TestCase):
    def test_format_accepts_multiple_paths(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["format", "a.pas", "b.pas", "--check"])
        self.assertEqual(args.paths, ["a.pas", "b.pas"])
        self.assertTrue(args.check)

    def test_format_mutual_exclusion_write_check(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            # Argparse exits on mutually-exclusive flags.
            with redirect_stderr(io.StringIO()):
                parser.parse_args(["format", "x.pas", "--write", "--check"])

    def test_check_accepts_multiple_paths(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["check", "a.pas", "b.pas"])
        self.assertEqual(args.paths, ["a.pas", "b.pas"])


class CliFormatTests(unittest.TestCase):
    def test_directory_without_mode_errors(self) -> None:
        """Directory input without --write/--diff/--check must error out."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write(base / "a.pas", UNFORMATTED_SRC)
            buf = io.StringIO()
            with redirect_stderr(buf), redirect_stdout(io.StringIO()):
                rc = main(["format", str(base)])
            self.assertEqual(rc, 2)
            self.assertIn("requires one of", buf.getvalue())

    def test_directory_check_mode_returns_1_when_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write(base / "a.pas", UNFORMATTED_SRC)
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                rc = main(["format", str(base), "--check"])
            self.assertEqual(rc, 1)

    def test_directory_write_mode_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            target = base / "a.pas"
            _write(target, UNFORMATTED_SRC)
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                rc1 = main(["format", str(base), "--write"])
            self.assertEqual(rc1, 0)
            first = target.read_text(encoding="utf-8")
            self.assertNotEqual(first, UNFORMATTED_SRC)

            # Second run shouldn't change anything.
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                rc2 = main(["format", str(base), "--check"])
            self.assertEqual(rc2, 0)

    def test_single_file_no_mode_prints_to_stdout(self) -> None:
        """Backward-compat: single file + no mode flag -> formatted output on stdout."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            target = base / "a.pas"
            _write(target, UNFORMATTED_SRC)
            out = io.StringIO()
            err = io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = main(["format", str(target)])
            self.assertEqual(rc, 0)
            # Source file itself untouched.
            self.assertEqual(target.read_text(encoding="utf-8"), UNFORMATTED_SRC)
            # Stdout carries formatted output (keywords lowercased by default cfg).
            self.assertIn("begin", out.getvalue())

    def test_nonexistent_path_returns_2(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            missing = base / "nope"
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                rc = main(["format", str(missing), "--check"])
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()

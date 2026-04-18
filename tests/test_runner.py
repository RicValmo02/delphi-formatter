"""Tests for the directory-aware driver (`runner.py`)."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from delphi_formatter.config import default_config
from delphi_formatter.runner import (
    DEFAULT_EXCLUDES,
    DEFAULT_INCLUDES,
    Mode,
    Verbosity,
    iter_source_files,
    run,
)


# Small but non-trivial Delphi snippet that the default config will reformat
# (keywords are uppercase in the input, the default config lowercases them).
UNFORMATTED_SRC = "BEGIN IF X THEN Y ELSE Z; END;\n"
# Already-clean unit; idempotent under the default config.
CLEAN_SRC = "begin\n  if x then\n    y\n  else\n    z;\nend;\n"


def _write(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding, newline="")


def _make_project(base: Path) -> dict[str, Path]:
    """Create a mini Delphi project structure under *base* and return key paths."""
    files = {
        "a":      base / "src" / "a.pas",
        "b":      base / "src" / "sub" / "b.pas",
        "binjunk": base / "src" / "bin" / "obsolete.pas",
        "dpr":    base / "src" / "weird.dpr",
        "obj":    base / "src" / "obj" / "cache.pas",
    }
    for p in files.values():
        _write(p, UNFORMATTED_SRC)
    return files


# ---------------------------------------------------------------------------
# iter_source_files
# ---------------------------------------------------------------------------


class IterSourceFilesTests(unittest.TestCase):
    def test_walks_directory_and_picks_up_pas_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            files = _make_project(base)
            got = iter_source_files([base])
            got_abs = {p.resolve() for p in got}
            self.assertIn(files["a"].resolve(), got_abs)
            self.assertIn(files["b"].resolve(), got_abs)

    def test_default_excludes_drop_bin_and_obj(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            files = _make_project(base)
            got = iter_source_files([base])
            got_abs = {p.resolve() for p in got}
            self.assertNotIn(files["binjunk"].resolve(), got_abs)
            self.assertNotIn(files["obj"].resolve(), got_abs)

    def test_default_excludes_catch_top_level_bin(self) -> None:
        """Regression: `**/bin/**` must exclude `bin/` at the root too."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            junk = base / "bin" / "skip_me.pas"
            ok = base / "src" / "keep.pas"
            _write(junk, UNFORMATTED_SRC)
            _write(ok, UNFORMATTED_SRC)
            got = iter_source_files([base])
            got_abs = {p.resolve() for p in got}
            self.assertIn(ok.resolve(), got_abs)
            self.assertNotIn(junk.resolve(), got_abs)

    def test_default_includes_skip_dpr(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            files = _make_project(base)
            got = iter_source_files([base])
            got_abs = {p.resolve() for p in got}
            self.assertNotIn(files["dpr"].resolve(), got_abs)

    def test_custom_include_picks_up_dpr(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            files = _make_project(base)
            got = iter_source_files([base], includes=("*.pas", "*.dpr"))
            got_abs = {p.resolve() for p in got}
            self.assertIn(files["dpr"].resolve(), got_abs)

    def test_custom_exclude_skips_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            files = _make_project(base)
            got = iter_source_files(
                [base],
                excludes=DEFAULT_EXCLUDES + ("**/sub/**",),
            )
            got_abs = {p.resolve() for p in got}
            self.assertIn(files["a"].resolve(), got_abs)
            self.assertNotIn(files["b"].resolve(), got_abs)

    def test_explicit_file_bypasses_include_filter(self) -> None:
        """A .dpr passed directly should be kept even though defaults skip it."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            files = _make_project(base)
            got = iter_source_files([files["dpr"]])
            self.assertEqual([p.resolve() for p in got], [files["dpr"].resolve()])

    def test_deduplication(self) -> None:
        """Passing dir+file shouldn't yield the same path twice."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            files = _make_project(base)
            got = iter_source_files([base / "src", files["a"]])
            got_abs = [p.resolve() for p in got]
            self.assertEqual(len(got_abs), len(set(got_abs)))

    def test_missing_path_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with self.assertRaises(FileNotFoundError):
                iter_source_files([base / "does_not_exist"])

    def test_sorted_output(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _make_project(base)
            got = iter_source_files([base])
            strs = [str(p.resolve()).lower() for p in got]
            self.assertEqual(strs, sorted(strs))


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


class RunCheckModeTests(unittest.TestCase):
    def test_check_reports_changes_and_exits_1(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _make_project(base)
            stdout, stderr = io.StringIO(), io.StringIO()
            summary = run(
                [base],
                default_config(),
                Mode.CHECK,
                stdout=stdout, stderr=stderr,
            )
            self.assertGreater(summary.n_changed, 0)
            self.assertEqual(summary.n_errors, 0)
            self.assertEqual(summary.exit_code(Mode.CHECK), 1)
            # Files themselves aren't touched.
            self.assertEqual(
                (base / "src" / "a.pas").read_text(encoding="utf-8"),
                UNFORMATTED_SRC,
            )

    def test_check_on_clean_project_exits_0(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write(base / "src" / "a.pas", CLEAN_SRC)
            stdout, stderr = io.StringIO(), io.StringIO()
            summary = run(
                [base],
                default_config(),
                Mode.CHECK,
                stdout=stdout, stderr=stderr,
            )
            self.assertEqual(summary.n_changed, 0)
            self.assertEqual(summary.exit_code(Mode.CHECK), 0)


class RunWriteModeTests(unittest.TestCase):
    def test_write_rewrites_file_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            files = _make_project(base)

            stdout, stderr = io.StringIO(), io.StringIO()
            summary = run(
                [base],
                default_config(),
                Mode.WRITE,
                stdout=stdout, stderr=stderr,
            )
            self.assertGreater(summary.n_written, 0)
            self.assertEqual(summary.n_errors, 0)
            self.assertEqual(summary.exit_code(Mode.WRITE), 0)

            # File content has actually changed on disk.
            first = files["a"].read_text(encoding="utf-8")
            self.assertNotEqual(first, UNFORMATTED_SRC)

            # Second run: nothing left to change.
            stdout2, stderr2 = io.StringIO(), io.StringIO()
            summary2 = run(
                [base],
                default_config(),
                Mode.WRITE,
                stdout=stdout2, stderr=stderr2,
            )
            self.assertEqual(summary2.n_changed, 0)
            self.assertEqual(summary2.n_written, 0)

            # Content is stable.
            self.assertEqual(files["a"].read_text(encoding="utf-8"), first)


class RunDiffModeTests(unittest.TestCase):
    def test_diff_writes_to_stdout_and_leaves_files_alone(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            files = _make_project(base)
            stdout, stderr = io.StringIO(), io.StringIO()
            summary = run(
                [base],
                default_config(),
                Mode.DIFF,
                stdout=stdout, stderr=stderr,
            )
            self.assertGreater(summary.n_changed, 0)
            diff_text = stdout.getvalue()
            self.assertIn("---", diff_text)
            self.assertIn("+++", diff_text)
            # File untouched on disk.
            self.assertEqual(
                files["a"].read_text(encoding="utf-8"),
                UNFORMATTED_SRC,
            )


class RunErrorHandlingTests(unittest.TestCase):
    def test_decode_error_is_per_file_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            ok = base / "src" / "a.pas"
            broken = base / "src" / "broken.pas"
            _write(ok, UNFORMATTED_SRC)
            # Non-UTF-8 bytes (ISO-8859-1 é-like sequence that is invalid UTF-8
            # at position 0).
            broken.parent.mkdir(parents=True, exist_ok=True)
            broken.write_bytes(b"\xff\xfe\xfd\xfc not utf8\n")

            stdout, stderr = io.StringIO(), io.StringIO()
            summary = run(
                [base],
                default_config(),
                Mode.CHECK,
                stdout=stdout, stderr=stderr,
            )
            # Both files processed; broken reported as error.
            self.assertEqual(summary.n_total, 2)
            self.assertEqual(summary.n_errors, 1)
            self.assertEqual(summary.exit_code(Mode.CHECK), 1)
            # Error line is on stderr.
            self.assertIn("error:", stderr.getvalue())
            self.assertIn("broken.pas", stderr.getvalue())


class RunVerbosityTests(unittest.TestCase):
    def test_quiet_suppresses_per_file_output(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _make_project(base)
            stdout, stderr = io.StringIO(), io.StringIO()
            run(
                [base],
                default_config(),
                Mode.CHECK,
                verbosity=Verbosity.QUIET,
                stdout=stdout, stderr=stderr,
            )
            # No per-file "would reformat" lines in quiet mode.
            self.assertNotIn("would reformat", stderr.getvalue())

    def test_verbose_prints_unchanged_lines(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write(base / "src" / "a.pas", CLEAN_SRC)
            stdout, stderr = io.StringIO(), io.StringIO()
            run(
                [base],
                default_config(),
                Mode.CHECK,
                verbosity=Verbosity.VERBOSE,
                stdout=stdout, stderr=stderr,
            )
            self.assertIn("unchanged:", stderr.getvalue())


# ---------------------------------------------------------------------------
# Pair processing (.pas + sibling .dfm)
# ---------------------------------------------------------------------------


# A minimal VCL-like pair: the TForm1 class holds Button1: TButton and the
# DFM declares the matching `object Button1: TButton`.
_FORM_PAS = (
    "unit Unit1;\n"
    "interface\n"
    "uses Forms, StdCtrls;\n"
    "type\n"
    "  TForm1 = class(TForm)\n"
    "    Button1: TButton;\n"
    "  end;\n"
    "var\n"
    "  Form1: TForm1;\n"
    "implementation\n"
    "{$R *.dfm}\n"
    "end.\n"
)

_FORM_DFM = (
    "object Form1: TForm1\n"
    "  Caption = 'Demo'\n"
    "  object Button1: TButton\n"
    "    Caption = 'OK'\n"
    "    OnClick = Button1Click\n"
    "  end\n"
    "end\n"
)


def _pair_bytype_config() -> dict:
    """Config that renames TButton -> btn and allows form-class touches."""
    cfg = default_config()
    cfg["variablePrefix"]["skipVisualComponents"] = False
    cfg["variablePrefix"]["byType"]["enabled"] = True
    cfg["variablePrefix"]["byType"]["rules"] = [
        {"typePattern": "TButton", "prefix": "btn"},
    ]
    return cfg


class PairWriteModeTests(unittest.TestCase):
    def test_write_rewrites_both_pas_and_dfm(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pas = base / "Unit1.pas"
            dfm = base / "Unit1.dfm"
            _write(pas, _FORM_PAS)
            _write(dfm, _FORM_DFM)

            stdout, stderr = io.StringIO(), io.StringIO()
            summary = run(
                [pas],
                _pair_bytype_config(),
                Mode.WRITE,
                stdout=stdout, stderr=stderr,
            )
            self.assertEqual(summary.n_errors, 0)
            self.assertEqual(summary.exit_code(Mode.WRITE), 0)

            new_pas = pas.read_text(encoding="utf-8")
            new_dfm = dfm.read_text(encoding="utf-8")
            self.assertIn("btnButton1: TButton", new_pas)
            self.assertIn("object btnButton1: TButton", new_dfm)
            # Event handler is never renamed.
            self.assertIn("OnClick = Button1Click", new_dfm)

    def test_write_idempotent_on_second_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pas = base / "Unit1.pas"
            dfm = base / "Unit1.dfm"
            _write(pas, _FORM_PAS)
            _write(dfm, _FORM_DFM)

            cfg = _pair_bytype_config()
            run([pas], cfg, Mode.WRITE,
                stdout=io.StringIO(), stderr=io.StringIO())

            pas_first = pas.read_text(encoding="utf-8")
            dfm_first = dfm.read_text(encoding="utf-8")

            summary2 = run([pas], cfg, Mode.WRITE,
                stdout=io.StringIO(), stderr=io.StringIO())
            self.assertEqual(summary2.n_written, 0)
            self.assertEqual(pas.read_text(encoding="utf-8"), pas_first)
            self.assertEqual(dfm.read_text(encoding="utf-8"), dfm_first)


class PairCheckModeTests(unittest.TestCase):
    def test_check_flags_pair_as_changed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pas = base / "Unit1.pas"
            dfm = base / "Unit1.dfm"
            _write(pas, _FORM_PAS)
            _write(dfm, _FORM_DFM)

            stdout, stderr = io.StringIO(), io.StringIO()
            summary = run(
                [pas],
                _pair_bytype_config(),
                Mode.CHECK,
                stdout=stdout, stderr=stderr,
            )
            self.assertGreaterEqual(summary.n_changed, 1)
            self.assertEqual(summary.exit_code(Mode.CHECK), 1)
            self.assertIn("would reformat", stderr.getvalue())
            self.assertIn("sibling", stderr.getvalue())
            # Files untouched on disk.
            self.assertEqual(pas.read_text(encoding="utf-8"), _FORM_PAS)
            self.assertEqual(dfm.read_text(encoding="utf-8"), _FORM_DFM)


class PairDiffModeTests(unittest.TestCase):
    def test_diff_emits_both_pas_and_dfm_diffs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pas = base / "Unit1.pas"
            dfm = base / "Unit1.dfm"
            _write(pas, _FORM_PAS)
            _write(dfm, _FORM_DFM)

            stdout, stderr = io.StringIO(), io.StringIO()
            run(
                [pas],
                _pair_bytype_config(),
                Mode.DIFF,
                stdout=stdout, stderr=stderr,
            )
            diff_text = stdout.getvalue()
            # Two unified diffs back-to-back on stdout.
            self.assertIn(str(pas), diff_text)
            self.assertIn(str(dfm), diff_text)
            # Files untouched on disk.
            self.assertEqual(pas.read_text(encoding="utf-8"), _FORM_PAS)
            self.assertEqual(dfm.read_text(encoding="utf-8"), _FORM_DFM)


class PairBinaryDfmTests(unittest.TestCase):
    def test_binary_dfm_reports_error_and_leaves_pas_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pas = base / "Unit1.pas"
            dfm = base / "Unit1.dfm"
            _write(pas, _FORM_PAS)
            # Magic TPF0 marks a binary DFM.
            dfm.write_bytes(b"TPF0\x01\x02\x03whatever")

            stdout, stderr = io.StringIO(), io.StringIO()
            summary = run(
                [pas],
                _pair_bytype_config(),
                Mode.WRITE,
                stdout=stdout, stderr=stderr,
            )
            self.assertEqual(summary.n_errors, 1)
            self.assertIn("binary", stderr.getvalue().lower())
            # pas must NOT be rewritten.
            self.assertEqual(pas.read_text(encoding="utf-8"), _FORM_PAS)


class PairNoSiblingTests(unittest.TestCase):
    def test_pas_without_sibling_dfm_runs_normally(self) -> None:
        # When there's no sibling .dfm, the feature flag only affects
        # ancestor-based detection — and here the class doesn't inherit
        # from TForm, so the rename goes through without surprises.
        src = (
            "unit U;\n"
            "interface\n"
            "type TFoo = class(TObject)\n"
            "  Button1: TButton;\n"
            "end;\n"
            "implementation\n"
            "end.\n"
        )
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pas = base / "U.pas"
            _write(pas, src)
            stdout, stderr = io.StringIO(), io.StringIO()
            summary = run(
                [pas],
                _pair_bytype_config(),
                Mode.WRITE,
                stdout=stdout, stderr=stderr,
            )
            self.assertEqual(summary.n_errors, 0)
            self.assertIn("btnButton1: TButton", pas.read_text(encoding="utf-8"))


class PairCaseInsensitiveSiblingTests(unittest.TestCase):
    def test_finds_uppercase_dfm_extension(self) -> None:
        """Case-insensitive match: Form1.pas + Form1.DFM must pair."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pas = base / "Unit1.pas"
            # Use an uppercase .DFM extension.
            dfm = base / "Unit1.DFM"
            _write(pas, _FORM_PAS)
            _write(dfm, _FORM_DFM)

            stdout, stderr = io.StringIO(), io.StringIO()
            summary = run(
                [pas],
                _pair_bytype_config(),
                Mode.WRITE,
                stdout=stdout, stderr=stderr,
            )
            self.assertEqual(summary.n_errors, 0)
            self.assertIn("object btnButton1: TButton",
                          dfm.read_text(encoding="utf-8"))


class PairSafeDefaultTests(unittest.TestCase):
    def test_skip_visual_true_leaves_pair_alone(self) -> None:
        """With skipVisualComponents=True (default), form pair untouched."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            pas = base / "Unit1.pas"
            dfm = base / "Unit1.dfm"
            _write(pas, _FORM_PAS)
            _write(dfm, _FORM_DFM)

            cfg = _pair_bytype_config()
            cfg["variablePrefix"]["skipVisualComponents"] = True

            stdout, stderr = io.StringIO(), io.StringIO()
            summary = run(
                [pas],
                cfg,
                Mode.WRITE,
                stdout=stdout, stderr=stderr,
            )
            # pas might be touched for formatting, but Button1 remains.
            new_pas = pas.read_text(encoding="utf-8")
            self.assertNotIn("btnButton1", new_pas)
            self.assertEqual(dfm.read_text(encoding="utf-8"), _FORM_DFM)
            self.assertEqual(summary.n_errors, 0)


if __name__ == "__main__":
    unittest.main()

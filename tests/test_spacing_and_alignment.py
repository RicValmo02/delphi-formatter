import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from delphi_formatter.config import default_config
from delphi_formatter.formatter import format_source


def _quiet_cfg() -> dict:
    cfg = default_config()
    cfg["keywords"]["case"] = "preserve"
    cfg["builtinTypes"]["case"] = "preserve"
    cfg["variablePrefix"]["local"]["enabled"] = False
    cfg["variablePrefix"]["classField"]["enabled"] = False
    cfg["variablePrefix"]["byType"]["enabled"] = False
    return cfg


class SpacingTests(unittest.TestCase):
    def test_space_inserted_around_assignment(self) -> None:
        cfg = _quiet_cfg()
        cfg["spacing"]["aroundOperators"] = True
        cfg["alignment"]["alignVarColons"] = False
        src = "x:=1;"
        out = format_source(src, cfg)
        self.assertIn("x := 1", out)

    def test_space_inserted_after_comma(self) -> None:
        cfg = _quiet_cfg()
        cfg["spacing"]["afterComma"] = True
        cfg["alignment"]["alignVarColons"] = False
        src = "a,b,c"
        out = format_source(src, cfg)
        self.assertIn("a, b, c", out)


class AssignmentSpacingTests(unittest.TestCase):
    """Fine-grained control over ':=' (e.g. num := 5)."""

    def _cfg(self, *, before: bool, after: bool) -> dict:
        cfg = _quiet_cfg()
        cfg["alignment"]["alignVarColons"] = False
        cfg["spacing"]["assignment"] = {"spaceBefore": before, "spaceAfter": after}
        return cfg

    def test_default_is_space_before_and_after(self) -> None:
        cfg = _quiet_cfg()
        cfg["alignment"]["alignVarColons"] = False
        out = format_source("x:=1;", cfg)
        self.assertIn("x := 1", out)

    def test_only_space_before(self) -> None:
        out = format_source("x:=1;", self._cfg(before=True, after=False))
        self.assertIn("x :=1", out)
        self.assertNotIn(":= 1", out)

    def test_only_space_after(self) -> None:
        out = format_source("x:=1;", self._cfg(before=False, after=True))
        self.assertIn("x:= 1", out)
        self.assertNotIn("x :=", out)

    def test_no_space_either_side(self) -> None:
        out = format_source("x := 1;", self._cfg(before=False, after=False))
        self.assertIn("x:=1", out)

    def test_collapses_double_space_before(self) -> None:
        out = format_source("x   :=  1;", self._cfg(before=True, after=True))
        self.assertIn("x := 1", out)
        self.assertNotIn("x  :=", out)


class DeclarationColonSpacingTests(unittest.TestCase):
    """Fine-grained control over ':' in declarations (e.g. 'var num: Integer')."""

    def _cfg(self, *, before: bool, after: bool) -> dict:
        cfg = _quiet_cfg()
        cfg["alignment"]["alignVarColons"] = False  # don't let alignment win
        cfg["spacing"]["declarationColon"] = {
            "spaceBefore": before,
            "spaceAfter": after,
        }
        return cfg

    def test_default_is_tight_before_space_after(self) -> None:
        cfg = _quiet_cfg()
        cfg["alignment"]["alignVarColons"] = False
        out = format_source(
            "var\n  num:Integer;\nbegin\nend;\n", cfg
        )
        self.assertIn("num: Integer", out)
        self.assertNotIn("num : Integer", out)

    def test_space_before_colon(self) -> None:
        out = format_source(
            "var\n  num: Integer;\nbegin\nend;\n",
            self._cfg(before=True, after=True),
        )
        self.assertIn("num : Integer", out)

    def test_no_space_after_colon(self) -> None:
        out = format_source(
            "var\n  num: Integer;\nbegin\nend;\n",
            self._cfg(before=False, after=False),
        )
        self.assertIn("num:Integer", out)
        self.assertNotIn("num : Integer", out)
        self.assertNotIn("num: Integer", out)

    def test_colon_config_does_not_affect_assignment(self) -> None:
        """Changing declarationColon must NOT change the ':=' formatting."""
        cfg = self._cfg(before=True, after=False)  # weird 'num :Integer'
        out = format_source("x:=5;", cfg)
        # Default assignment defaults still apply: space before AND after :=
        self.assertIn("x := 5", out)

    def test_alignment_still_wins_when_enabled(self) -> None:
        """With alignVarColons on, spacing.declarationColon.spaceBefore is
        overridden by the padding needed to align columns."""
        cfg = self._cfg(before=False, after=True)
        cfg["alignment"]["alignVarColons"] = True
        src = (
            "var\n"
            "  short: Integer;\n"
            "  muchLongerName: string;\n"
            "begin\n"
            "end;\n"
        )
        out = format_source(src, cfg)
        # Both ':' columns should be aligned despite spaceBefore=False, so
        # 'short' gets extra padding.
        decl_lines = [
            ln for ln in out.splitlines()
            if ":" in ln and ln.strip().split(":")[0].strip()
            in ("short", "muchLongerName")
        ]
        self.assertEqual(len(decl_lines), 2)
        cols = [ln.index(":") for ln in decl_lines]
        self.assertEqual(cols[0], cols[1], f"colons not aligned: {decl_lines}")


class AlignmentTests(unittest.TestCase):
    def test_align_var_colons(self) -> None:
        cfg = _quiet_cfg()
        cfg["alignment"]["alignVarColons"] = True
        src = (
            "var\n"
            "  short: Integer;\n"
            "  muchLongerName: string;\n"
            "  x: Boolean;\n"
            "begin\n"
            "end;\n"
        )
        out = format_source(src, cfg)
        lines = out.splitlines()
        colon_cols = [ln.index(":") for ln in lines if ":" in ln and not ln.strip().startswith(("begin", "var"))]
        self.assertTrue(len(colon_cols) >= 3)
        self.assertEqual(len(set(colon_cols)), 1)


class WhitespaceTests(unittest.TestCase):
    def test_trims_trailing(self) -> None:
        cfg = _quiet_cfg()
        src = "x := 1;   \ny := 2;\t\n"
        out = format_source(src, cfg)
        for ln in out.splitlines():
            self.assertEqual(ln, ln.rstrip())

    def test_ensure_final_newline(self) -> None:
        cfg = _quiet_cfg()
        src = "x := 1;"
        out = format_source(src, cfg)
        self.assertTrue(out.endswith("\n"))

    def test_collapse_blank_lines(self) -> None:
        cfg = _quiet_cfg()
        cfg["blankLines"]["maxConsecutive"] = 1
        src = "a\n\n\n\n\nb\n"
        out = format_source(src, cfg)
        self.assertNotIn("\n\n\n", out)


if __name__ == "__main__":
    unittest.main()

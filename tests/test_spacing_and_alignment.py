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

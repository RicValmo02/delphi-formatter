import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from delphi_formatter.config import default_config
from delphi_formatter.formatter import format_source


class KeywordCaseTests(unittest.TestCase):
    def test_lowercase_keywords(self) -> None:
        cfg = default_config()
        cfg["keywords"]["case"] = "lower"
        src = "BEGIN IF X THEN Y ELSE Z; END;"
        out = format_source(src, cfg)
        # All keywords lowercased, identifiers preserved
        self.assertIn("begin", out)
        self.assertIn("if", out)
        self.assertIn("then", out)
        self.assertIn("else", out)
        self.assertIn("end", out)
        self.assertIn("X", out)  # identifier preserved

    def test_uppercase_keywords(self) -> None:
        cfg = default_config()
        cfg["keywords"]["case"] = "upper"
        src = "begin if x then y else z; end;"
        out = format_source(src, cfg)
        self.assertIn("BEGIN", out)
        self.assertIn("IF", out)
        self.assertIn("THEN", out)

    def test_preserve_keeps_case(self) -> None:
        cfg = default_config()
        cfg["keywords"]["case"] = "preserve"
        cfg["builtinTypes"]["case"] = "preserve"
        cfg["spacing"]["aroundOperators"] = False
        cfg["spacing"]["afterComma"] = False
        cfg["blankLines"]["collapseConsecutive"] = False
        cfg["endOfFile"]["ensureFinalNewline"] = False
        cfg["endOfFile"]["trimTrailingWhitespace"] = False
        cfg["alignment"]["alignVarColons"] = False
        cfg["alignment"]["alignConstEquals"] = False
        cfg["variablePrefix"]["local"]["enabled"] = False
        cfg["variablePrefix"]["classField"]["enabled"] = False
        cfg["variablePrefix"]["byType"]["enabled"] = False
        src = "Begin IF x THEN y ELSE z; end;\n"
        out = format_source(src, cfg)
        self.assertEqual(out, src)

    def test_builtin_types_case(self) -> None:
        cfg = default_config()
        cfg["keywords"]["case"] = "preserve"
        cfg["builtinTypes"]["case"] = "lower"
        src = "var x: INTEGER; y: STRING;"
        out = format_source(src, cfg)
        self.assertIn("integer", out)
        self.assertIn("string", out)


if __name__ == "__main__":
    unittest.main()

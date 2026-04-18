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


class MatchKeywordsTests(unittest.TestCase):
    """builtinTypes.case = 'match-keywords' tracks keywords.case."""

    def _src(self) -> str:
        return (
            "PROCEDURE Demo;\n"
            "VAR\n"
            "  a: String;\n"
            "  b: Integer;\n"
            "  c: Boolean;\n"
            "  d: Char;\n"
            "  e: TDateTime;\n"
            "BEGIN\n"
            "END;\n"
        )

    def test_match_keywords_follows_lower(self) -> None:
        cfg = default_config()
        cfg["keywords"]["case"] = "lower"
        cfg["builtinTypes"]["case"] = "match-keywords"
        cfg["alignment"]["alignVarColons"] = False
        out = format_source(self._src(), cfg)
        # Every built-in type lowercased
        for t in ("string", "integer", "boolean", "char", "tdatetime"):
            self.assertIn(t, out)
        # And not the capitalised originals
        for t in ("Integer", "Boolean", "Char", "TDateTime"):
            self.assertNotIn(t, out)

    def test_match_keywords_follows_upper(self) -> None:
        cfg = default_config()
        cfg["keywords"]["case"] = "upper"
        cfg["builtinTypes"]["case"] = "match-keywords"
        cfg["alignment"]["alignVarColons"] = False
        out = format_source(self._src(), cfg)
        for t in ("STRING", "INTEGER", "BOOLEAN", "CHAR", "TDATETIME"):
            self.assertIn(t, out)

    def test_match_keywords_follows_preserve(self) -> None:
        """When keywords=preserve, built-in types also stay untouched."""
        cfg = default_config()
        cfg["keywords"]["case"] = "preserve"
        cfg["builtinTypes"]["case"] = "match-keywords"
        cfg["spacing"]["aroundOperators"] = False
        cfg["spacing"]["afterComma"] = False
        cfg["blankLines"]["collapseConsecutive"] = False
        cfg["endOfFile"]["ensureFinalNewline"] = False
        cfg["endOfFile"]["trimTrailingWhitespace"] = False
        cfg["alignment"]["alignVarColons"] = False
        cfg["spacing"]["declarationColon"] = {
            "spaceBefore": False,
            "spaceAfter": True,
        }
        cfg["spacing"]["assignment"] = {"spaceBefore": True, "spaceAfter": True}
        src = "var x: Integer;"
        out = format_source(src, cfg)
        # Integer kept capitalised because match-keywords resolves to preserve.
        self.assertIn("Integer", out)

    def test_validation_accepts_match_keywords(self) -> None:
        from delphi_formatter.config import validate_config
        cfg = default_config()
        cfg["builtinTypes"]["case"] = "match-keywords"
        self.assertEqual(validate_config(cfg), [])

    def test_validation_rejects_bogus_value(self) -> None:
        from delphi_formatter.config import validate_config
        cfg = default_config()
        cfg["builtinTypes"]["case"] = "bogus"
        errs = validate_config(cfg)
        self.assertTrue(any("builtinTypes.case" in e for e in errs))


if __name__ == "__main__":
    unittest.main()

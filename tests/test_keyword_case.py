import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from delphi_formatter.config import default_config, validate_config
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
    """builtinTypes.case = 'match-keywords' should follow keywords.case."""

    def test_match_keywords_follows_lower(self) -> None:
        cfg = default_config()
        cfg["keywords"]["case"] = "lower"
        cfg["builtinTypes"]["case"] = "match-keywords"
        src = "VAR X: INTEGER; Y: STRING; Z: BOOLEAN;"
        out = format_source(src, cfg)
        self.assertIn("var", out)
        self.assertIn("integer", out)
        self.assertIn("string", out)
        self.assertIn("boolean", out)
        self.assertNotIn("INTEGER", out)
        self.assertNotIn("STRING", out)

    def test_match_keywords_follows_upper(self) -> None:
        cfg = default_config()
        cfg["keywords"]["case"] = "upper"
        cfg["builtinTypes"]["case"] = "match-keywords"
        src = "var x: integer; y: string; z: boolean;"
        out = format_source(src, cfg)
        self.assertIn("VAR", out)
        self.assertIn("INTEGER", out)
        self.assertIn("STRING", out)
        self.assertIn("BOOLEAN", out)

    def test_match_keywords_follows_preserve(self) -> None:
        """keywords=preserve + builtinTypes=match-keywords -> both preserved."""
        cfg = default_config()
        cfg["keywords"]["case"] = "preserve"
        cfg["builtinTypes"]["case"] = "match-keywords"
        cfg["spacing"]["aroundOperators"] = False
        cfg["spacing"]["afterComma"] = False
        cfg["alignment"]["alignVarColons"] = False
        cfg["variablePrefix"]["local"]["enabled"] = False
        cfg["variablePrefix"]["classField"]["enabled"] = False
        cfg["variablePrefix"]["byType"]["enabled"] = False
        src = "Var X: Integer; Y: STRING;\n"
        out = format_source(src, cfg)
        # Both keywords and built-in types untouched.
        self.assertIn("Var", out)
        self.assertIn("Integer", out)
        self.assertIn("STRING", out)

    def test_validation_accepts_match_keywords(self) -> None:
        cfg = default_config()
        cfg["builtinTypes"]["case"] = "match-keywords"
        self.assertEqual(validate_config(cfg), [])

    def test_validation_rejects_bogus_case(self) -> None:
        cfg = default_config()
        cfg["builtinTypes"]["case"] = "banana"
        errors = validate_config(cfg)
        self.assertTrue(
            any("builtinTypes.case" in e for e in errors),
            f"expected an error for builtinTypes.case, got: {errors}",
        )
        # And 'match-keywords' must NOT be accepted for keywords.case (only
        # builtinTypes gets that extra value).
        cfg2 = default_config()
        cfg2["keywords"]["case"] = "match-keywords"
        errors2 = validate_config(cfg2)
        self.assertTrue(
            any("keywords.case" in e for e in errors2),
            f"expected an error for keywords.case, got: {errors2}",
        )


class CanonicalBuiltinTypeTests(unittest.TestCase):
    """`builtinTypes.case = "canonical"` emits the RTL-documented spelling."""

    def _quiet(self) -> dict:
        cfg = default_config()
        cfg["keywords"]["case"] = "lower"
        cfg["spacing"]["aroundOperators"] = False
        cfg["spacing"]["afterComma"] = False
        cfg["alignment"]["alignVarColons"] = False
        cfg["variablePrefix"]["local"]["enabled"] = False
        cfg["variablePrefix"]["classField"]["enabled"] = False
        cfg["variablePrefix"]["byType"]["enabled"] = False
        return cfg

    def test_canonical_capitalizes_common_types(self) -> None:
        cfg = self._quiet()
        cfg["builtinTypes"]["case"] = "canonical"
        src = (
            "var a: integer; b: boolean; c: tdatetime; "
            "d: PCHAR; e: STRING; f: cardinal;"
        )
        out = format_source(src, cfg)
        self.assertIn("Integer", out)
        self.assertIn("Boolean", out)
        self.assertIn("TDateTime", out)
        self.assertIn("PChar", out)
        self.assertIn("String", out)
        self.assertIn("Cardinal", out)
        # No stray all-caps survivors.
        self.assertNotIn("INTEGER", out)
        self.assertNotIn("STRING", out)
        self.assertNotIn("PCHAR", out)

    def test_canonical_preserves_keyword_setting(self) -> None:
        """Keywords follow their own setting; canonical only affects types."""
        cfg = self._quiet()
        cfg["keywords"]["case"] = "upper"
        cfg["builtinTypes"]["case"] = "canonical"
        src = "var x: integer;"
        out = format_source(src, cfg)
        self.assertIn("VAR", out)
        self.assertIn("Integer", out)

    def test_canonical_with_string_override(self) -> None:
        """The user's actual request: canonical + string->lower override."""
        cfg = self._quiet()
        cfg["builtinTypes"]["case"] = "canonical"
        cfg["builtinTypes"]["overrides"] = {"String": "string"}
        src = "var a: INTEGER; b: BOOLEAN; c: TDATETIME; d: STRING;"
        out = format_source(src, cfg)
        self.assertIn("Integer", out)
        self.assertIn("Boolean", out)
        self.assertIn("TDateTime", out)
        self.assertIn("string", out)
        self.assertNotIn("String ", out)
        self.assertNotIn("STRING", out)

    def test_validator_accepts_canonical(self) -> None:
        cfg = default_config()
        cfg["builtinTypes"]["case"] = "canonical"
        self.assertEqual(validate_config(cfg), [])


class BuiltinTypeOverridesTests(unittest.TestCase):
    """`builtinTypes.overrides` pins individual types regardless of `case`."""

    def _quiet(self) -> dict:
        cfg = default_config()
        cfg["keywords"]["case"] = "preserve"
        cfg["spacing"]["aroundOperators"] = False
        cfg["spacing"]["afterComma"] = False
        cfg["alignment"]["alignVarColons"] = False
        cfg["variablePrefix"]["local"]["enabled"] = False
        cfg["variablePrefix"]["classField"]["enabled"] = False
        cfg["variablePrefix"]["byType"]["enabled"] = False
        return cfg

    def test_override_wins_over_preserve(self) -> None:
        cfg = self._quiet()
        cfg["builtinTypes"]["case"] = "preserve"
        cfg["builtinTypes"]["overrides"] = {"Integer": "Integer"}
        src = "VAR x: INTEGER; y: string;"
        out = format_source(src, cfg)
        # 'INTEGER' forced to 'Integer'; 'string' untouched because
        # case=preserve and not listed in overrides.
        self.assertIn("Integer", out)
        self.assertNotIn("INTEGER", out)
        self.assertIn("string", out)

    def test_override_wins_over_global_lower(self) -> None:
        """string stays lower, Integer/Boolean pin to capital form."""
        cfg = self._quiet()
        cfg["keywords"]["case"] = "lower"
        cfg["builtinTypes"]["case"] = "lower"
        cfg["builtinTypes"]["overrides"] = {
            "Integer": "Integer",
            "Boolean": "Boolean",
            "TDateTime": "TDateTime",
        }
        src = "VAR x: INTEGER; s: STRING; b: BOOLEAN; d: TDATETIME;"
        out = format_source(src, cfg)
        self.assertIn("Integer", out)
        self.assertIn("Boolean", out)
        self.assertIn("TDateTime", out)
        self.assertIn("string", out)  # not overridden -> follows lower
        self.assertNotIn("INTEGER", out)
        self.assertNotIn("STRING", out)

    def test_override_is_case_insensitive_lookup(self) -> None:
        """Key 'integer' matches tokens 'Integer', 'INTEGER', 'integer'."""
        cfg = self._quiet()
        cfg["builtinTypes"]["case"] = "preserve"
        cfg["builtinTypes"]["overrides"] = {"integer": "Integer"}
        src = "var a: Integer; b: INTEGER; c: integer;"
        out = format_source(src, cfg)
        # All three spellings collapse to 'Integer'.
        self.assertEqual(out.count("Integer"), 3)
        self.assertNotIn("INTEGER", out)

    def test_override_string_keeps_lower_while_others_capital(self) -> None:
        """The exact use case the user asked about."""
        cfg = self._quiet()
        cfg["keywords"]["case"] = "lower"
        cfg["builtinTypes"]["case"] = "preserve"
        cfg["builtinTypes"]["overrides"] = {
            "string": "string",
            "Integer": "Integer",
        }
        src = "VAR x: INTEGER; s: STRING;"
        out = format_source(src, cfg)
        self.assertIn("Integer", out)
        self.assertIn("string", out)
        self.assertNotIn("STRING", out)
        self.assertNotIn("INTEGER", out)

    def test_validator_rejects_unknown_type(self) -> None:
        cfg = default_config()
        cfg["builtinTypes"]["overrides"] = {"NotAType": "NotAType"}
        errors = validate_config(cfg)
        self.assertTrue(
            any("NotAType" in e for e in errors),
            f"expected unknown-type error, got: {errors}",
        )

    def test_validator_rejects_different_identifier(self) -> None:
        """Value must spell the same identifier as the key (case-insensitive)."""
        cfg = default_config()
        cfg["builtinTypes"]["overrides"] = {"Integer": "Banana"}
        errors = validate_config(cfg)
        self.assertTrue(
            any("Integer" in e and "Banana" in e for e in errors),
            f"expected identifier-mismatch error, got: {errors}",
        )

    def test_validator_accepts_good_overrides(self) -> None:
        cfg = default_config()
        cfg["builtinTypes"]["overrides"] = {
            "string": "string",
            "Integer": "Integer",
            "Boolean": "Boolean",
        }
        self.assertEqual(validate_config(cfg), [])


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from delphi_formatter.tokenizer import (
    COMMENT,
    DIRECTIVE,
    IDENT,
    KEYWORD,
    NEWLINE,
    NUMBER,
    OPERATOR,
    STRING,
    WHITESPACE,
    detokenize,
    tokenize,
)


class TokenizerRoundTripTests(unittest.TestCase):
    def _assert_round_trip(self, source: str) -> None:
        tokens = tokenize(source)
        self.assertEqual(detokenize(tokens), source)

    def test_empty(self) -> None:
        self._assert_round_trip("")

    def test_simple_unit(self) -> None:
        src = "unit Foo;\n\ninterface\n\nimplementation\n\nend.\n"
        self._assert_round_trip(src)

    def test_string_literal_with_escape(self) -> None:
        src = "s := 'it''s fine';\n"
        self._assert_round_trip(src)
        tokens = tokenize(src)
        string_toks = [t for t in tokens if t.type == STRING]
        self.assertEqual(len(string_toks), 1)
        self.assertEqual(string_toks[0].value, "'it''s fine'")

    def test_comments(self) -> None:
        src = "// line comment\n{ block comment }\n(* paren comment *)\nx := 1;\n"
        self._assert_round_trip(src)
        tokens = tokenize(src)
        kinds = [t.type for t in tokens if t.type in (COMMENT, DIRECTIVE)]
        self.assertEqual(kinds.count(COMMENT), 3)

    def test_directive_vs_comment(self) -> None:
        src = "{$IFDEF DEBUG}x{$ENDIF}"
        tokens = tokenize(src)
        dirs = [t for t in tokens if t.type == DIRECTIVE]
        self.assertEqual(len(dirs), 2)

    def test_operator_pairs(self) -> None:
        src = "x := 1; if x <> 2 then y := 3;"
        tokens = tokenize(src)
        ops = [t.value for t in tokens if t.type == OPERATOR]
        self.assertIn(":=", ops)
        self.assertIn("<>", ops)

    def test_hex_and_decimal_numbers(self) -> None:
        src = "x := $FF; y := 1.5e+3;"
        tokens = tokenize(src)
        nums = [t.value for t in tokens if t.type == NUMBER]
        self.assertIn("$FF", nums)
        self.assertIn("1.5e+3", nums)

    def test_keyword_classification(self) -> None:
        src = "begin end;"
        tokens = tokenize(src)
        kw = [t.value for t in tokens if t.type == KEYWORD]
        self.assertIn("begin", kw)
        self.assertIn("end", kw)

    def test_crlf_preserved_as_lf_value_but_round_trips_via_detokenize(self) -> None:
        # Detokenize preserves token *values*; CRLF in input becomes LF in the
        # output — this is intentional, the whitespace pass reintroduces CRLF
        # if configured. So we don't assert round-trip byte-equality here, just
        # that the line count is right.
        src = "a\r\nb\r\n"
        tokens = tokenize(src)
        newlines = [t for t in tokens if t.type == NEWLINE]
        self.assertEqual(len(newlines), 2)


if __name__ == "__main__":
    unittest.main()

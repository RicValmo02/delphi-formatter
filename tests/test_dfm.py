"""Tests for :mod:`delphi_formatter.dfm` — the textual-DFM parser and the
positional rename propagation.

The parser is deliberately small and permissive; the core invariant we
care about is that :func:`apply_rename` never breaks byte-layout outside
the spans it intends to touch, and that it never rewrites event handlers.
"""

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from delphi_formatter.dfm import (
    DfmParseError,
    VK_BARE_IDENT,
    VK_BINARY,
    VK_COLLECTION,
    VK_NUMBER,
    VK_SET,
    VK_STRING,
    apply_rename,
    is_binary_dfm,
    parse_dfm,
)


class IsBinaryDfmTests(unittest.TestCase):
    def test_tpf0_magic_is_binary(self) -> None:
        self.assertTrue(is_binary_dfm(b"TPF0\x01\x02\x03"))

    def test_text_header_is_not_binary(self) -> None:
        self.assertFalse(is_binary_dfm(b"object Form1: TForm"))

    def test_empty_is_not_binary(self) -> None:
        self.assertFalse(is_binary_dfm(b""))

    def test_short_prefix_is_not_binary(self) -> None:
        self.assertFalse(is_binary_dfm(b"TPF"))


class ParseSimpleObjectTests(unittest.TestCase):
    def test_flat_object_parses(self) -> None:
        text = (
            "object Form1: TForm\n"
            "  Left = 0\n"
            "  Top = 0\n"
            "  Caption = 'Hello'\n"
            "end\n"
        )
        root = parse_dfm(text)
        self.assertEqual(root.header_kind, "object")
        self.assertEqual(root.name, "Form1")
        self.assertEqual(root.type_name, "TForm")
        self.assertEqual([p.name for p in root.properties], ["Left", "Top", "Caption"])
        # Spans should be consistent with the source.
        self.assertEqual(text[slice(*root.name_span)], "Form1")
        self.assertEqual(text[slice(*root.type_span)], "TForm")

    def test_inline_header_recognised(self) -> None:
        text = "inline Frame1: TFrame1\nend\n"
        root = parse_dfm(text)
        self.assertEqual(root.header_kind, "inline")
        self.assertEqual(root.name, "Frame1")

    def test_inherited_header_recognised(self) -> None:
        text = "inherited Dlg: TDialog\nend\n"
        root = parse_dfm(text)
        self.assertEqual(root.header_kind, "inherited")

    def test_raises_on_garbage(self) -> None:
        with self.assertRaises(DfmParseError):
            parse_dfm("this is not a dfm\n")


class ParsePropertyKindsTests(unittest.TestCase):
    def test_number_value(self) -> None:
        text = "object A: TX\n  Left = 42\nend\n"
        root = parse_dfm(text)
        p = root.properties[0]
        self.assertEqual(p.value_kind, VK_NUMBER)
        self.assertEqual(p.value_text, "42")
        self.assertEqual(text[p.value_start:p.value_end], "42")

    def test_string_value_with_concat(self) -> None:
        # Delphi DFM concatenation: 'a'#13#10'b' must be one STRING span.
        text = "object A: TX\n  Caption = 'a'#13#10'b'\nend\n"
        root = parse_dfm(text)
        p = root.properties[0]
        self.assertEqual(p.value_kind, VK_STRING)
        self.assertEqual(text[p.value_start:p.value_end], "'a'#13#10'b'")

    def test_bare_ident_value(self) -> None:
        text = "object A: TX\n  DataSource = dsMain\nend\n"
        root = parse_dfm(text)
        p = root.properties[0]
        self.assertEqual(p.value_kind, VK_BARE_IDENT)
        self.assertEqual(p.value_text, "dsMain")

    def test_set_value(self) -> None:
        text = "object A: TX\n  Style = [fsBold, fsItalic]\nend\n"
        root = parse_dfm(text)
        p = root.properties[0]
        self.assertEqual(p.value_kind, VK_SET)

    def test_binary_block_value(self) -> None:
        text = (
            "object A: TX\n"
            "  Picture.Data = {\n"
            "    0A 0B 0C 0D}\n"
            "end\n"
        )
        root = parse_dfm(text)
        p = root.properties[0]
        self.assertEqual(p.value_kind, VK_BINARY)
        self.assertEqual(p.name, "Picture.Data")

    def test_collection_value(self) -> None:
        text = (
            "object A: TX\n"
            "  Columns = <\n"
            "    item\n"
            "      Width = 10\n"
            "    end>\n"
            "end\n"
        )
        root = parse_dfm(text)
        p = root.properties[0]
        self.assertEqual(p.value_kind, VK_COLLECTION)

    def test_qualified_property_name(self) -> None:
        text = "object A: TX\n  Font.Size = 10\nend\n"
        root = parse_dfm(text)
        p = root.properties[0]
        self.assertEqual(p.name, "Font.Size")

    def test_event_detection(self) -> None:
        text = (
            "object A: TX\n"
            "  OnClick = BtnClick\n"
            "  Columns.OnColumnClick = GridColClick\n"
            "  Caption = Hello\n"
            "end\n"
        )
        root = parse_dfm(text)
        by_name = {p.name: p for p in root.properties}
        self.assertTrue(by_name["OnClick"].is_event)
        # Qualified event: last dotted segment starts with "On".
        self.assertTrue(by_name["Columns.OnColumnClick"].is_event)
        self.assertFalse(by_name["Caption"].is_event)


class ParseNestingTests(unittest.TestCase):
    def test_nested_children(self) -> None:
        text = (
            "object Form1: TForm\n"
            "  object Panel1: TPanel\n"
            "    object Button1: TButton\n"
            "      Caption = 'OK'\n"
            "    end\n"
            "  end\n"
            "end\n"
        )
        root = parse_dfm(text)
        self.assertEqual(len(root.children), 1)
        panel = root.children[0]
        self.assertEqual(panel.name, "Panel1")
        self.assertEqual(len(panel.children), 1)
        button = panel.children[0]
        self.assertEqual(button.name, "Button1")
        self.assertEqual(button.type_name, "TButton")

    def test_bom_prefix_is_tolerated(self) -> None:
        text = "\ufeffobject Form1: TForm\nend\n"
        root = parse_dfm(text)
        self.assertEqual(root.name, "Form1")


class ApplyRenameTests(unittest.TestCase):
    def _roundtrip(self, text: str, rename_map: dict[str, str]) -> str:
        root = parse_dfm(text)
        return apply_rename(text, root, rename_map)

    def test_empty_map_returns_unchanged_text(self) -> None:
        text = "object Form1: TForm\n  Caption = 'hi'\nend\n"
        out = self._roundtrip(text, {})
        self.assertEqual(out, text)

    def test_no_matching_entries_returns_unchanged(self) -> None:
        text = "object Form1: TForm\n  Caption = 'hi'\nend\n"
        out = self._roundtrip(text, {"Other": "renamed"})
        self.assertEqual(out, text)

    def test_renames_header_name(self) -> None:
        text = "object Button1: TButton\n  Caption = 'OK'\nend\n"
        out = self._roundtrip(text, {"Button1": "btnOK"})
        self.assertIn("object btnOK: TButton", out)
        # Everything else preserved byte-for-byte.
        self.assertIn("  Caption = 'OK'\n", out)
        self.assertEqual(out.count("end\n"), 1)

    def test_renames_bare_ident_rhs(self) -> None:
        text = (
            "object Grid1: TDBGrid\n"
            "  DataSource = DataSource1\n"
            "end\n"
        )
        out = self._roundtrip(text, {"DataSource1": "dsMain"})
        self.assertIn("DataSource = dsMain\n", out)

    def test_skips_event_handlers(self) -> None:
        # Button1Click is a method name; it must never be renamed even if
        # it appears in rename_map. The formatter's rename map only ever
        # contains field names, but we defensively test it anyway.
        text = (
            "object Button1: TButton\n"
            "  OnClick = Button1Click\n"
            "end\n"
        )
        out = self._roundtrip(text, {"Button1Click": "WhateverClick"})
        self.assertIn("OnClick = Button1Click\n", out)

    def test_skips_qualified_events(self) -> None:
        text = (
            "object Grid1: TDBGrid\n"
            "  Columns.OnColumnClick = GridColClick\n"
            "end\n"
        )
        out = self._roundtrip(text, {"GridColClick": "OtherClick"})
        self.assertIn("Columns.OnColumnClick = GridColClick\n", out)

    def test_case_insensitive_match(self) -> None:
        text = "object BUTTON1: TButton\nend\n"
        out = self._roundtrip(text, {"button1": "btn1"})
        self.assertIn("object btn1: TButton", out)

    def test_replacement_uses_map_value_spelling(self) -> None:
        # The map value's exact spelling wins, regardless of how the source
        # spelled the original identifier.
        text = "object button1: TButton\nend\n"
        out = self._roundtrip(text, {"Button1": "btnOK"})
        self.assertIn("object btnOK: TButton", out)

    def test_does_not_rename_enum_inside_set(self) -> None:
        # fsBold inside a set is NOT a bare-ident RHS (the RHS kind is SET,
        # not BARE_IDENT), so it must not be touched even if it's in the map.
        text = "object A: TX\n  Style = [fsBold, fsItalic]\nend\n"
        out = self._roundtrip(text, {"fsBold": "xxx"})
        self.assertEqual(out, text)

    def test_does_not_rename_property_name(self) -> None:
        # The LHS of `=` is a property name; even if it collides with a map
        # key, we never rewrite it.
        text = "object A: TX\n  Caption = 'hello'\nend\n"
        out = self._roundtrip(text, {"Caption": "xxx"})
        self.assertEqual(out, text)

    def test_renames_inside_nested_children(self) -> None:
        text = (
            "object Form1: TForm\n"
            "  object Panel1: TPanel\n"
            "    object Button1: TButton\n"
            "      Caption = 'OK'\n"
            "    end\n"
            "  end\n"
            "end\n"
        )
        out = self._roundtrip(text, {"Button1": "btnOK", "Panel1": "pnlMain"})
        self.assertIn("object pnlMain: TPanel", out)
        self.assertIn("object btnOK: TButton", out)
        # Form1 not in map, stays put.
        self.assertIn("object Form1: TForm", out)

    def test_preserves_whitespace_and_comments(self) -> None:
        # Indented with tabs, line comment in the middle, trailing spaces:
        # the untouched regions must be byte-identical after apply_rename.
        text = (
            "object Form1: TForm   \n"
            "\t// a comment before Button1\n"
            "\tobject Button1: TButton\n"
            "\t\tCaption = 'OK'\n"
            "\tend\n"
            "end\n"
        )
        out = self._roundtrip(text, {"Button1": "btnOK"})
        # The only change should be the identifier inside the object header.
        expected = text.replace("Button1: TButton", "btnOK: TButton")
        self.assertEqual(out, expected)

    def test_preserves_crlf_line_endings(self) -> None:
        text = "object Form1: TForm\r\n  Caption = 'hi'\r\nend\r\n"
        out = self._roundtrip(text, {"Form1": "frmMain"})
        self.assertIn("object frmMain: TForm\r\n", out)
        # No stray LF-only lines.
        self.assertEqual(out.count("\r\n"), 3)

    def test_bare_ident_inside_binary_block_not_renamed(self) -> None:
        # Picture.Data = {...} is opaque to us; even if it contained something
        # that looked like an identifier, we must not touch it.
        text = (
            "object A: TX\n"
            "  Picture.Data = {\n"
            "    Button1\n"
            "  }\n"
            "end\n"
        )
        out = self._roundtrip(text, {"Button1": "btnOK"})
        # Binary block left untouched.
        self.assertIn("Button1", out)


if __name__ == "__main__":
    unittest.main()

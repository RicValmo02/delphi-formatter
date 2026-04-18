"""End-to-end tests for the VCL-form safety feature.

The scenarios we care about, one per test:

* ``skipVisualComponents=True`` (the default) leaves form fields alone —
  whether form-class detection happens via ancestor inheritance, via a
  sibling ``.dfm``, or both.
* ``skipVisualComponents=False`` renames form fields **and** patches the
  sibling ``.dfm`` in sync, producing a coherent pair.
* Binary DFMs are rejected with a clean error and the ``.pas`` is left
  untouched (pair atomicity).
* Non-form classes with e.g. a ``TButton`` field still get renamed even
  when the feature is enabled — the safety net is scoped to form classes.
"""

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from delphi_formatter.config import default_config, validate_config
from delphi_formatter.formatter import format_pas_with_dfm, format_source
from delphi_formatter.rules.identifier_prefix import ClassScope, is_form_class


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _bytype_config(skip_visual: bool) -> dict:
    """Config with byType enabled (TButton -> btn) and F-prefix fields."""
    cfg = default_config()
    cfg["variablePrefix"]["skipVisualComponents"] = skip_visual
    cfg["variablePrefix"]["classField"]["enabled"] = True
    cfg["variablePrefix"]["classField"]["prefix"] = "F"
    cfg["variablePrefix"]["byType"]["enabled"] = True
    cfg["variablePrefix"]["byType"]["rules"] = [
        {"typePattern": "TButton", "prefix": "btn"},
    ]
    return cfg


_FORM_PAS = """\
unit Unit1;

interface

uses
  Forms, StdCtrls;

type
  TForm1 = class(TForm)
    Button1: TButton;
    procedure Button1Click(Sender: TObject);
  end;

var
  Form1: TForm1;

implementation

{$R *.dfm}

procedure TForm1.Button1Click(Sender: TObject);
begin
  Button1.Caption := 'hi';
end;

end.
"""

_FORM_DFM = """\
object Form1: TForm1
  Caption = 'Demo'
  object Button1: TButton
    Caption = 'OK'
    OnClick = Button1Click
  end
end
"""


# ---------------------------------------------------------------------------
# is_form_class unit tests
# ---------------------------------------------------------------------------


class FormClassDetectionTests(unittest.TestCase):
    def test_detects_tform_ancestor(self) -> None:
        cls = ClassScope(keyword_idx=0, end_idx=0, name="TForm1", ancestor_names=["TForm"])
        self.assertTrue(is_form_class(cls))

    def test_detects_tframe_ancestor(self) -> None:
        cls = ClassScope(keyword_idx=0, end_idx=0, name="TFrame1", ancestor_names=["TFrame"])
        self.assertTrue(is_form_class(cls))

    def test_detects_tdatamodule_ancestor(self) -> None:
        cls = ClassScope(keyword_idx=0, end_idx=0, name="TDM", ancestor_names=["TDataModule"])
        self.assertTrue(is_form_class(cls))

    def test_detects_tcustomform_ancestor(self) -> None:
        cls = ClassScope(keyword_idx=0, end_idx=0, name="TBase", ancestor_names=["TCustomForm"])
        self.assertTrue(is_form_class(cls))

    def test_case_insensitive(self) -> None:
        cls = ClassScope(keyword_idx=0, end_idx=0, name="TFormX", ancestor_names=["tform"])
        self.assertTrue(is_form_class(cls))

    def test_plain_class_not_a_form(self) -> None:
        cls = ClassScope(keyword_idx=0, end_idx=0, name="TFoo", ancestor_names=["TObject"])
        self.assertFalse(is_form_class(cls))

    def test_no_ancestors_not_a_form(self) -> None:
        cls = ClassScope(keyword_idx=0, end_idx=0, name="TFoo", ancestor_names=[])
        self.assertFalse(is_form_class(cls))

    def test_sibling_dfm_overrides_ancestor_check(self) -> None:
        cls = ClassScope(keyword_idx=0, end_idx=0, name="TFoo", ancestor_names=["TObject"])
        self.assertTrue(is_form_class(cls, has_dfm_sibling=True))


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class ConfigSkipVisualTests(unittest.TestCase):
    def test_default_is_true(self) -> None:
        cfg = default_config()
        self.assertTrue(cfg["variablePrefix"]["skipVisualComponents"])

    def test_validator_accepts_bool(self) -> None:
        cfg = default_config()
        cfg["variablePrefix"]["skipVisualComponents"] = False
        self.assertEqual(validate_config(cfg), [])

    def test_validator_rejects_non_bool(self) -> None:
        cfg = default_config()
        cfg["variablePrefix"]["skipVisualComponents"] = "yes"
        errs = validate_config(cfg)
        self.assertTrue(any("skipVisualComponents" in e for e in errs))


# ---------------------------------------------------------------------------
# Form skip behaviour via `format_source` (PAS-only API)
# ---------------------------------------------------------------------------


class SkipVisualComponentsTrueTests(unittest.TestCase):
    """Default safe mode: form fields are NOT renamed."""

    def test_tform_ancestor_skipped(self) -> None:
        cfg = _bytype_config(skip_visual=True)
        out = format_source(_FORM_PAS, cfg)
        # No 'btnButton1' anywhere — the form field stays 'Button1'.
        self.assertNotIn("btnButton1", out)
        self.assertIn("Button1: TButton", out)

    def test_sibling_dfm_flag_skipped(self) -> None:
        # No TForm ancestor, but caller signals a sibling DFM exists.
        src = (
            "unit U; interface type TFoo = class(TObject)\n"
            "  Button1: TButton;\n"
            "end;\n"
            "implementation end.\n"
        )
        cfg = _bytype_config(skip_visual=True)
        out = format_source(src, cfg, has_dfm_sibling=True)
        self.assertNotIn("btnButton1", out)
        self.assertIn("Button1: TButton", out)


class SkipVisualComponentsFalseTests(unittest.TestCase):
    """Opt-in mode: form fields ARE renamed."""

    def test_tform_ancestor_gets_renamed(self) -> None:
        cfg = _bytype_config(skip_visual=False)
        out = format_source(_FORM_PAS, cfg)
        self.assertIn("btnButton1: TButton", out)
        # Method call inside body is rewritten too.
        self.assertIn("btnButton1.Caption", out)


# ---------------------------------------------------------------------------
# Pair orchestration via `format_pas_with_dfm`
# ---------------------------------------------------------------------------


class PairFormattingTests(unittest.TestCase):
    def test_pair_renames_pas_and_dfm_coherently(self) -> None:
        cfg = _bytype_config(skip_visual=False)
        result = format_pas_with_dfm(_FORM_PAS, _FORM_DFM, cfg)
        self.assertIsNone(result.dfm_error)
        # pas side: renamed
        self.assertIn("btnButton1: TButton", result.pas_text_after)
        # dfm side: renamed header, event handler LEFT ALONE.
        self.assertIsNotNone(result.dfm_text_after)
        assert result.dfm_text_after is not None  # for type-checkers
        self.assertIn("object btnButton1: TButton", result.dfm_text_after)
        self.assertIn("OnClick = Button1Click", result.dfm_text_after)
        # The rename map propagated to the caller.
        self.assertEqual(result.report.field_rename_map, {"Button1": "btnButton1"})

    def test_pair_true_default_leaves_both_untouched(self) -> None:
        cfg = _bytype_config(skip_visual=True)
        result = format_pas_with_dfm(_FORM_PAS, _FORM_DFM, cfg)
        # No rename map means the DFM was never rewritten.
        self.assertEqual(result.report.field_rename_map, {})
        self.assertIsNone(result.dfm_text_after)
        # pas is formatted but `Button1` remains the form field name.
        self.assertIn("Button1: TButton", result.pas_text_after)
        self.assertNotIn("btnButton1", result.pas_text_after)

    def test_no_rename_means_no_dfm_rewrite(self) -> None:
        # All prefixes disabled -> empty rename map -> dfm_text_after is None
        # even when a DFM is supplied.
        cfg = default_config()
        cfg["variablePrefix"]["skipVisualComponents"] = False
        result = format_pas_with_dfm(_FORM_PAS, _FORM_DFM, cfg)
        self.assertEqual(result.report.field_rename_map, {})
        self.assertIsNone(result.dfm_text_after)

    def test_binary_dfm_rejected_pas_untouched(self) -> None:
        # A 'TPF0...' prefix triggers binary detection; the pas must be
        # returned verbatim and an error recorded.
        cfg = _bytype_config(skip_visual=False)
        binary_dfm = "TPF0\x01\x02\x03whatever"
        result = format_pas_with_dfm(_FORM_PAS, binary_dfm, cfg)
        self.assertIsNotNone(result.dfm_error)
        self.assertIn("binary", result.dfm_error or "")
        # pas_text_after is the input verbatim (no formatting applied).
        self.assertEqual(result.pas_text_after, _FORM_PAS)

    def test_no_dfm_falls_back_to_pas_only(self) -> None:
        cfg = _bytype_config(skip_visual=False)
        result = format_pas_with_dfm(_FORM_PAS, None, cfg)
        # Without a DFM, has_dfm_sibling is False, so without a TForm
        # ancestor the class wouldn't be treated as a form; here we DO
        # inherit from TForm so the rename is still skipped... unless
        # the feature is off. Let's verify: feature=false -> renamed.
        self.assertIn("btnButton1", result.pas_text_after)
        self.assertIsNone(result.dfm_text_after)


class NonFormClassStillRenamedTests(unittest.TestCase):
    """Non-form classes must NOT be exempted just because a TButton appears."""

    def test_plain_class_button_field_renamed(self) -> None:
        src = (
            "unit U;\n"
            "interface\n"
            "type\n"
            "  TFoo = class(TObject)\n"
            "    Button1: TButton;\n"
            "  end;\n"
            "implementation\n"
            "end.\n"
        )
        # Even with skip_visual=True, a plain class that has a TButton field
        # is NOT a form — rename goes through.
        cfg = _bytype_config(skip_visual=True)
        out = format_source(src, cfg)
        self.assertIn("btnButton1: TButton", out)


if __name__ == "__main__":
    unittest.main()

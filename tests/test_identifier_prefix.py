import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from delphi_formatter.config import default_config
from delphi_formatter.formatter import format_source


def _minimal_cfg() -> dict:
    cfg = default_config()
    cfg["keywords"]["case"] = "preserve"
    cfg["builtinTypes"]["case"] = "preserve"
    cfg["alignment"]["alignVarColons"] = False
    cfg["alignment"]["alignConstEquals"] = False
    cfg["spacing"]["aroundOperators"] = False
    cfg["spacing"]["afterComma"] = False
    return cfg


class LocalPrefixTests(unittest.TestCase):
    def test_local_var_gets_L_prefix(self) -> None:
        cfg = _minimal_cfg()
        cfg["variablePrefix"]["local"]["enabled"] = True
        cfg["variablePrefix"]["local"]["prefix"] = "L"
        cfg["variablePrefix"]["byType"]["enabled"] = False
        src = (
            "procedure Foo;\n"
            "var\n"
            "  ciao: string;\n"
            "begin\n"
            "  ciao := 'hi';\n"
            "end;\n"
        )
        out = format_source(src, cfg)
        self.assertIn("LCiao: string", out)
        self.assertIn("LCiao := 'hi'", out)
        self.assertNotIn(" ciao:", out)

    def test_global_var_not_touched(self) -> None:
        cfg = _minimal_cfg()
        cfg["variablePrefix"]["local"]["enabled"] = True
        cfg["variablePrefix"]["byType"]["enabled"] = False
        src = (
            "unit U;\n"
            "interface\n"
            "var\n"
            "  globalName: Integer;\n"
            "implementation\n"
            "end.\n"
        )
        out = format_source(src, cfg)
        self.assertIn("globalName", out)
        self.assertNotIn("LGlobalName", out)

    def test_local_not_applied_to_member_access(self) -> None:
        """After a `.`, identifiers are properties — never rename them."""
        cfg = _minimal_cfg()
        cfg["variablePrefix"]["local"]["enabled"] = True
        cfg["variablePrefix"]["byType"]["enabled"] = False
        src = (
            "procedure Foo;\n"
            "var\n"
            "  caption: string;\n"
            "begin\n"
            "  button.caption := caption;\n"
            "end;\n"
        )
        out = format_source(src, cfg)
        # declaration + assignment target/source renamed; property access not
        self.assertIn("LCaption: string", out)
        self.assertIn("button.caption", out)
        self.assertIn(":= LCaption", out)


class ClassFieldPrefixTests(unittest.TestCase):
    def test_field_gets_F_prefix_unit_wide(self) -> None:
        cfg = _minimal_cfg()
        cfg["variablePrefix"]["classField"]["enabled"] = True
        cfg["variablePrefix"]["byType"]["enabled"] = False
        src = (
            "type\n"
            "  TFoo = class\n"
            "  private\n"
            "    data: Integer;\n"
            "  public\n"
            "    procedure Bump;\n"
            "  end;\n"
            "implementation\n"
            "procedure TFoo.Bump;\n"
            "begin\n"
            "  data := data + 1;\n"
            "end;\n"
        )
        out = format_source(src, cfg)
        self.assertIn("FData: Integer", out)
        self.assertIn("FData := FData + 1", out)


class TypePrefixTests(unittest.TestCase):
    def test_type_prefix_overrides_local(self) -> None:
        cfg = _minimal_cfg()
        cfg["variablePrefix"]["local"]["enabled"] = True
        cfg["variablePrefix"]["byType"]["enabled"] = True
        src = (
            "procedure Foo;\n"
            "var\n"
            "  myButton: TButton;\n"
            "begin\n"
            "  myButton.Caption := 'hi';\n"
            "end;\n"
        )
        out = format_source(src, cfg)
        # byType rule for TButton is "btn" -> "btnMyButton"
        self.assertIn("btnMyButton: TButton", out)
        self.assertIn("btnMyButton.Caption", out)

    def test_regex_type_pattern(self) -> None:
        cfg = _minimal_cfg()
        cfg["variablePrefix"]["local"]["enabled"] = False
        cfg["variablePrefix"]["byType"]["enabled"] = True
        # Default rules include `TList.*` -> lst
        src = (
            "procedure Foo;\n"
            "var\n"
            "  items: TListBox;\n"
            "begin\n"
            "  items.Clear;\n"
            "end;\n"
        )
        out = format_source(src, cfg)
        self.assertIn("lstItems: TListBox", out)

    def test_already_prefixed_not_double_prefixed(self) -> None:
        cfg = _minimal_cfg()
        cfg["variablePrefix"]["local"]["enabled"] = True
        cfg["variablePrefix"]["byType"]["enabled"] = False
        src = (
            "procedure Foo;\n"
            "var\n"
            "  LAlready: Integer;\n"
            "begin\n"
            "  LAlready := 0;\n"
            "end;\n"
        )
        out = format_source(src, cfg)
        self.assertIn("LAlready", out)
        self.assertNotIn("LLAlready", out)


if __name__ == "__main__":
    unittest.main()

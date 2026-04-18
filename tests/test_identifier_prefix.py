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
    # Disable parameter prefixing by default in these tests so each test can
    # opt in explicitly. Parameter prefix is ON by default in the real config,
    # but most tests below only care about one rule at a time.
    cfg["variablePrefix"]["parameter"]["enabled"] = False
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


class IdempotencyTests(unittest.TestCase):
    """Two consecutive ``format_source`` runs must produce identical output.

    Covers the subtle case where a name naturally starts with the prefix
    letter (``LengthArr``, ``Foo``): the first run treats it as unprefixed
    and renames it (``LLengthArr``, ``FFoo``); the second run sees the
    now-PascalCase-prefixed form (capital letter after the prefix) and
    correctly leaves it alone.

    Names that were already prefixed in the canonical form (``FName``,
    ``LCount``, ``btnSave``) must NOT be double-prefixed on the first run.
    """

    def test_two_runs_produce_identical_output(self) -> None:
        cfg = _minimal_cfg()
        cfg["variablePrefix"]["local"]["enabled"] = True
        cfg["variablePrefix"]["local"]["prefix"] = "L"
        cfg["variablePrefix"]["classField"]["enabled"] = True
        cfg["variablePrefix"]["classField"]["prefix"] = "F"
        cfg["variablePrefix"]["byType"]["enabled"] = True
        cfg["variablePrefix"]["byType"]["rules"] = [
            {"typePattern": "TButton", "prefix": "btn"},
        ]

        src = (
            "unit U;\n"
            "interface\n"
            "type\n"
            "  TFoo = class\n"
            "    Foo: Integer;\n"
            "    FName: string;\n"
            "    btnSave: TButton;\n"
            "    button1: TButton;\n"
            "  end;\n"
            "\n"
            "implementation\n"
            "\n"
            "procedure Demo;\n"
            "var\n"
            "  LengthArr: Integer;\n"
            "  LCount: Integer;\n"
            "  total: Integer;\n"
            "begin\n"
            "  LengthArr := 0;\n"
            "  LCount := 0;\n"
            "  total := 0;\n"
            "end;\n"
            "\n"
            "end.\n"
        )

        first = format_source(src, cfg)
        second = format_source(first, cfg)
        self.assertEqual(first, second, "format_source must be idempotent")

        # Sanity-check the first-run transformations the docs promise:
        self.assertIn("LLengthArr", first)   # L + engthArr → prefix applied
        self.assertIn("FFoo", first)         # F + oo → prefix applied
        self.assertIn("btnButton1", first)   # byType rename
        self.assertIn("LTotal", first)       # plain rename, capitalized

        # Names already prefixed in canonical form must NOT be touched:
        self.assertNotIn("LLCount", first)
        self.assertNotIn("FFName", first)
        self.assertNotIn("btnbtnSave", first)
        self.assertIn("LCount", first)
        self.assertIn("FName", first)
        self.assertIn("btnSave", first)


class ParameterPrefixTests(unittest.TestCase):
    """Parameter prefix: the ``A`` (argument) prefix applied to formal
    parameters in procedure/function signatures and their bodies.
    """

    def _param_cfg(self) -> dict:
        cfg = _minimal_cfg()
        cfg["variablePrefix"]["parameter"]["enabled"] = True
        cfg["variablePrefix"]["parameter"]["prefix"] = "A"
        cfg["variablePrefix"]["parameter"]["capitalizeAfterPrefix"] = True
        return cfg

    def test_single_param_renamed_in_signature_and_body(self) -> None:
        src = (
            "procedure Test(Value: Integer);\n"
            "begin\n"
            "  Value := Value + 1;\n"
            "end;\n"
        )
        out = format_source(src, self._param_cfg())
        self.assertIn("procedure Test(AValue: Integer)", out)
        self.assertIn("AValue := AValue + 1", out)
        self.assertNotIn(" Value ", out)

    def test_multiple_params_same_group(self) -> None:
        """``procedure Test(A, B: Integer; C: string);`` — each name gets
        its own 'A' prefix: ``AA, AB: Integer; AC: string``.
        """
        src = (
            "procedure Test(Value1, Value2: Integer; Msg: string);\n"
            "begin\n"
            "end;\n"
        )
        out = format_source(src, self._param_cfg())
        self.assertIn("AValue1", out)
        self.assertIn("AValue2", out)
        self.assertIn("AMsg", out)

    def test_modifiers_const_var_out_respected(self) -> None:
        src = (
            "procedure Test(const Value: Integer; var Ref: string; out Res: Integer);\n"
            "begin\n"
            "end;\n"
        )
        out = format_source(src, self._param_cfg())
        self.assertIn("const AValue: Integer", out)
        self.assertIn("var ARef: string", out)
        self.assertIn("out ARes: Integer", out)

    def test_default_value_param(self) -> None:
        src = (
            "procedure Test(Value: Integer = 0);\n"
            "begin\n"
            "end;\n"
        )
        out = format_source(src, self._param_cfg())
        self.assertIn("AValue: Integer = 0", out)

    def test_array_of_param(self) -> None:
        src = (
            "procedure Test(const Values: array of Integer);\n"
            "begin\n"
            "end;\n"
        )
        out = format_source(src, self._param_cfg())
        self.assertIn("const AValues: array of Integer", out)

    def test_already_prefixed_param_not_touched(self) -> None:
        """A parameter already named ``AValue`` must NOT become ``AAValue``."""
        src = (
            "procedure Test(AValue: Integer);\n"
            "begin\n"
            "  AValue := 0;\n"
            "end;\n"
        )
        out = format_source(src, self._param_cfg())
        self.assertIn("AValue", out)
        self.assertNotIn("AAValue", out)

    def test_call_site_not_touched(self) -> None:
        """The caller's locals passed as arguments must keep their name —
        only the formal parameter is rewritten.
        """
        src = (
            "procedure Callee(Value: Integer);\n"
            "begin\n"
            "end;\n"
            "\n"
            "procedure Caller;\n"
            "var\n"
            "  Anno: Integer;\n"
            "  Mese: Integer;\n"
            "begin\n"
            "  Callee(Anno);\n"
            "  Callee(Mese);\n"
            "end;\n"
        )
        out = format_source(src, self._param_cfg())
        # Callee's parameter is renamed...
        self.assertIn("procedure Callee(AValue: Integer)", out)
        # ...but the caller's locals and the argument positions are not.
        self.assertIn("Callee(Anno)", out)
        self.assertIn("Callee(Mese)", out)
        # The locals themselves are untouched (local prefix is off).
        self.assertIn("Anno: Integer", out)
        self.assertIn("Mese: Integer", out)

    def test_function_with_return_type(self) -> None:
        src = (
            "function Test(Value: Integer): Integer;\n"
            "begin\n"
            "  Result := Value * 2;\n"
            "end;\n"
        )
        out = format_source(src, self._param_cfg())
        self.assertIn("function Test(AValue: Integer): Integer", out)
        self.assertIn("Result := AValue * 2", out)

    def test_class_method_forward_and_impl_rename_coherently(self) -> None:
        """Forward declaration inside the class body AND the matching
        implementation header are both rewritten with the same prefix.
        """
        src = (
            "unit U;\n"
            "interface\n"
            "type\n"
            "  TFoo = class\n"
            "    procedure DoIt(Value: Integer);\n"
            "  end;\n"
            "implementation\n"
            "\n"
            "procedure TFoo.DoIt(Value: Integer);\n"
            "begin\n"
            "  Value := Value + 1;\n"
            "end;\n"
            "end.\n"
        )
        out = format_source(src, self._param_cfg())
        # Forward in class:
        self.assertIn("procedure DoIt(AValue: Integer);", out)
        # Implementation:
        self.assertIn("procedure TFoo.DoIt(AValue: Integer);", out)
        self.assertIn("AValue := AValue + 1", out)

    def test_forward_in_interface_is_renamed(self) -> None:
        """A plain forward at unit level (in ``interface``) still gets its
        parameters renamed, so the later implementation stays coherent.
        """
        src = (
            "unit U;\n"
            "interface\n"
            "procedure Test(Value: Integer);\n"
            "\n"
            "implementation\n"
            "\n"
            "procedure Test(Value: Integer);\n"
            "begin\n"
            "  Value := 0;\n"
            "end;\n"
            "end.\n"
        )
        out = format_source(src, self._param_cfg())
        # Both the interface forward and the impl header are rewritten.
        self.assertEqual(out.count("AValue: Integer"), 2)
        self.assertIn("AValue := 0", out)

    def test_parameter_wins_over_bytype(self) -> None:
        """A ``Button: TButton`` parameter with ``TButton -> btn`` byType
        rule must become ``AButton``, NOT ``btnButton``. Parameter prefix
        always wins over byType.
        """
        cfg = self._param_cfg()
        cfg["variablePrefix"]["byType"]["enabled"] = True
        cfg["variablePrefix"]["byType"]["rules"] = [
            {"typePattern": "TButton", "prefix": "btn"},
        ]
        src = (
            "procedure Test(Button: TButton);\n"
            "begin\n"
            "  Button.Caption := 'x';\n"
            "end;\n"
        )
        out = format_source(src, cfg)
        self.assertIn("procedure Test(AButton: TButton)", out)
        self.assertIn("AButton.Caption := 'x'", out)
        self.assertNotIn("btnButton", out)

    def test_disabled_leaves_params_alone(self) -> None:
        cfg = self._param_cfg()
        cfg["variablePrefix"]["parameter"]["enabled"] = False
        src = (
            "procedure Test(Value: Integer);\n"
            "begin\n"
            "  Value := 0;\n"
            "end;\n"
        )
        out = format_source(src, cfg)
        self.assertIn("procedure Test(Value: Integer)", out)
        self.assertNotIn("AValue", out)

    def test_nested_procedure_inner_params_renamed(self) -> None:
        """When a routine has a nested procedure, the inner routine's
        parameters are renamed (signature + body) independently.

        Known limitation (inherited from the scope finder): the outer
        routine that contains a nested ``procedure`` isn't detected as
        having a body, so only its signature is rewritten. Documented
        here rather than silently misleading users.
        """
        src = (
            "procedure Outer(OuterParam: Integer);\n"
            "  procedure Inner(InnerParam: Integer);\n"
            "  begin\n"
            "    InnerParam := InnerParam + 1;\n"
            "  end;\n"
            "begin\n"
            "  OuterParam := 0;\n"
            "end;\n"
        )
        out = format_source(src, self._param_cfg())
        # Inner's parameter is renamed everywhere inside Inner:
        self.assertIn("procedure Inner(AInnerParam: Integer)", out)
        self.assertIn("AInnerParam := AInnerParam + 1", out)
        # Outer's signature is rewritten too:
        self.assertIn("procedure Outer(AOuterParam: Integer)", out)

    def test_parameterless_routine_is_noop(self) -> None:
        src = (
            "procedure Test;\n"
            "begin\n"
            "end;\n"
        )
        out = format_source(src, self._param_cfg())
        self.assertIn("procedure Test;", out)
        self.assertNotIn("A:", out)

    def test_type_alias_procedure_not_touched(self) -> None:
        """``TFunc = function(x: Integer): Integer;`` is a type alias, not
        a routine — its parameter list must NOT be rewritten.
        """
        src = (
            "type\n"
            "  TFunc = function(Value: Integer): Integer;\n"
        )
        out = format_source(src, self._param_cfg())
        self.assertIn("function(Value: Integer): Integer", out)
        self.assertNotIn("AValue", out)

    def test_idempotent_with_parameter_prefix(self) -> None:
        src = (
            "procedure Test(Value: Integer; Anno: Integer);\n"
            "begin\n"
            "  Value := Anno;\n"
            "end;\n"
        )
        first = format_source(src, self._param_cfg())
        second = format_source(first, self._param_cfg())
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

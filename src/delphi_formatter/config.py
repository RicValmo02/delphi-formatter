"""Configuration handling for the Delphi formatter.

A config is a plain ``dict``. :func:`default_config` returns the full
default tree; user configs may be partial and are deep-merged on top.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


_DEFAULT: dict[str, Any] = {
    "indent": {
        "style": "spaces",          # "spaces" | "tabs"
        "size": 2,
        "continuationIndent": 2,
    },
    "keywords": {
        "case": "lower",            # "lower" | "upper" | "preserve"
    },
    "builtinTypes": {
        # "lower" | "upper" | "preserve" | "match-keywords"
        # "match-keywords" follows whatever 'keywords.case' is set to, so
        # 'String', 'Integer', 'Boolean', ... stay in sync with 'begin', 'if',
        # 'procedure', ... without having to configure the same value twice.
        "case": "preserve",
    },
    "variablePrefix": {
        # Safety net for VCL/FMX forms. When true (the safe default), classes
        # that inherit from TForm/TFrame/TDataModule/TCustomForm — or whose
        # .pas has a sibling .dfm — are left ALONE by the classField and
        # byType rename rules. Renaming a form field silently breaks the
        # .dfm binding unless the .dfm is updated too, so opting in should
        # be an explicit decision. Set false to let the formatter rename form
        # fields AND patch the sibling .dfm coherently.
        "skipVisualComponents": True,
        "local": {
            "enabled": False,
            "prefix": "L",
            "capitalizeAfterPrefix": True,
        },
        "classField": {
            "enabled": False,
            "prefix": "F",
            "capitalizeAfterPrefix": True,
        },
        # Parameters of procedures/functions/methods. Classic Delphi/Borland
        # convention is to prefix them with "A" (Argument): AValue, AIndex,
        # ASender. Rename propagates to every occurrence of the parameter name
        # inside the routine body AND the forward declaration header, but
        # NEVER touches the call site — a variable named `Anno` passed to
        # `Test(Mese, Anno)` stays `Anno`; only the formal parameter name in
        # `procedure Test(AMese, AAnno: Integer)` is rewritten.
        #
        # Unlike classField/local, this rule ALWAYS wins over byType: a
        # parameter `Button: TButton` with byType rule `TButton -> btn`
        # becomes `AButton`, not `btnButton`. The semantic "this is an
        # argument" trumps the type-based naming.
        "parameter": {
            "enabled": True,
            "prefix": "A",
            "capitalizeAfterPrefix": True,
        },
        "byType": {
            "enabled": False,
            "rules": [
                {"typePattern": "TButton",      "prefix": "btn"},
                {"typePattern": "TEdit",        "prefix": "edt"},
                {"typePattern": "TLabel",       "prefix": "lbl"},
                {"typePattern": "TForm",        "prefix": "frm"},
                {"typePattern": "TMemo",        "prefix": "mem"},
                {"typePattern": "TComboBox",    "prefix": "cbx"},
                {"typePattern": "TCheckBox",    "prefix": "chk"},
                {"typePattern": "TPanel",       "prefix": "pnl"},
                {"typePattern": "TStringList",  "prefix": "sl"},
                {"typePattern": "TList.*",      "prefix": "lst"},
            ],
            # When a variable matches both a scope prefix (local/classField)
            # AND a byType rule, which wins.
            "conflictResolution": "typePrefixOverridesScope",
        },
    },
    "alignment": {
        "alignAssignments": False,
        "alignVarColons": True,
        "alignConstEquals": True,
        "maxAlignSpaces": 40,
    },
    "spacing": {
        "aroundOperators": True,
        "afterComma": True,
        "beforeSemicolon": False,
        "insideParens": False,
        # Assignment operator ``:=`` (e.g. ``x := 5``).
        # These always apply regardless of ``aroundOperators``.
        "assignment": {
            "spaceBefore": True,
            "spaceAfter": True,
        },
        # Colon in declarations (e.g. ``num: Integer`` in a var/field/param
        # declaration). When ``alignment.alignVarColons`` is on, alignment
        # overrides the ``spaceBefore`` value to reach the aligned column.
        "declarationColon": {
            "spaceBefore": False,
            "spaceAfter": True,
        },
    },
    "blankLines": {
        "collapseConsecutive": True,
        "maxConsecutive": 1,
    },
    "endOfFile": {
        "trimTrailingWhitespace": True,
        "ensureFinalNewline": True,
        "lineEnding": "auto",       # "auto" | "crlf" | "lf"
    },
    "beginEndStyle": {
        # placeholder for future passes; kept for config stability
        "beginOnNewLine": True,
    },
}


def default_config() -> dict[str, Any]:
    """Return a fresh deep copy of the default configuration tree."""
    return copy.deepcopy(_DEFAULT)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge *override* onto *base* recursively (override wins). Pure function."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(path: str | Path | None) -> dict[str, Any]:
    """Load config from *path*, merging onto defaults. If path is None, return defaults."""
    cfg = default_config()
    if path is None:
        return cfg
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        user = json.load(f)
    if not isinstance(user, dict):
        raise ValueError(f"Config root must be a JSON object in {p}")
    return _deep_merge(cfg, user)


def save_config(config: dict[str, Any], path: str | Path) -> None:
    """Write *config* to *path* as pretty-printed JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


def validate_config(config: dict[str, Any]) -> list[str]:
    """Return a list of human-readable validation errors (empty if all OK)."""
    errors: list[str] = []

    def _check_case(path: str, value: Any, extra: tuple[str, ...] = ()) -> None:
        allowed = ("lower", "upper", "preserve") + extra
        if value not in allowed:
            pretty = ", ".join(repr(a) for a in allowed)
            errors.append(f"{path}: must be one of {pretty} (got {value!r})")

    if config.get("keywords", {}).get("case") is not None:
        _check_case("keywords.case", config["keywords"]["case"])
    if config.get("builtinTypes", {}).get("case") is not None:
        _check_case(
            "builtinTypes.case",
            config["builtinTypes"]["case"],
            extra=("match-keywords",),
        )

    indent = config.get("indent", {})
    if indent.get("style") not in ("spaces", "tabs"):
        errors.append(f"indent.style: must be 'spaces' or 'tabs' (got {indent.get('style')!r})")
    if not isinstance(indent.get("size"), int) or indent["size"] < 0:
        errors.append("indent.size: must be a non-negative integer")

    line_ending = config.get("endOfFile", {}).get("lineEnding")
    if line_ending not in ("auto", "crlf", "lf"):
        errors.append(f"endOfFile.lineEnding: must be 'auto', 'crlf' or 'lf' (got {line_ending!r})")

    spacing = config.get("spacing", {}) or {}
    for sub, keys in (
        ("assignment", ("spaceBefore", "spaceAfter")),
        ("declarationColon", ("spaceBefore", "spaceAfter")),
    ):
        node = spacing.get(sub)
        if node is None:
            continue
        if not isinstance(node, dict):
            errors.append(f"spacing.{sub}: must be an object")
            continue
        for k in keys:
            if k in node and not isinstance(node[k], bool):
                errors.append(f"spacing.{sub}.{k}: must be a boolean")

    vp = config.get("variablePrefix", {}) or {}
    if "skipVisualComponents" in vp and not isinstance(vp["skipVisualComponents"], bool):
        errors.append(
            "variablePrefix.skipVisualComponents: must be a boolean"
            f" (got {vp['skipVisualComponents']!r})"
        )

    # Sub-dict validators for local/classField/parameter: all share the same
    # {enabled: bool, prefix: str, capitalizeAfterPrefix: bool} schema.
    for sub in ("local", "classField", "parameter"):
        node = vp.get(sub)
        if node is None:
            continue
        if not isinstance(node, dict):
            errors.append(f"variablePrefix.{sub}: must be an object")
            continue
        if "enabled" in node and not isinstance(node["enabled"], bool):
            errors.append(f"variablePrefix.{sub}.enabled: must be a boolean")
        if "prefix" in node and not isinstance(node["prefix"], str):
            errors.append(f"variablePrefix.{sub}.prefix: must be a string")
        if "capitalizeAfterPrefix" in node and not isinstance(node["capitalizeAfterPrefix"], bool):
            errors.append(
                f"variablePrefix.{sub}.capitalizeAfterPrefix: must be a boolean"
            )

    by_type = vp.get("byType", {})
    rules = by_type.get("rules", [])
    if not isinstance(rules, list):
        errors.append("variablePrefix.byType.rules: must be a list")
    else:
        for idx, r in enumerate(rules):
            if not isinstance(r, dict):
                errors.append(f"variablePrefix.byType.rules[{idx}]: must be an object")
                continue
            if not isinstance(r.get("typePattern"), str):
                errors.append(f"variablePrefix.byType.rules[{idx}].typePattern: required string")
            if not isinstance(r.get("prefix"), str):
                errors.append(f"variablePrefix.byType.rules[{idx}].prefix: required string")

    return errors

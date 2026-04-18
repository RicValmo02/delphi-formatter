# delphi-formatter

A configurable formatter for **Delphi / Object Pascal** source code.

Everything is driven by a single JSON config file — casing of keywords,
variable-naming conventions (local / field / type-based prefixes),
spacing, alignment, blank-line policy, line endings, and more.

Written in pure Python (standard library only, no dependencies).

---

## Features

- **Keyword case** — force all Delphi reserved words to `lower`, `UPPER`,
  or leave them as the author wrote them.
- **Built-in type case** — separate policy for things like `Integer`,
  `String`, `Boolean`, `TDateTime`.
- **Local-variable prefix** — every variable declared inside a
  `procedure` / `function` `var` block is renamed with a configurable
  prefix (e.g. `ciao` → `LCiao`). Renaming is scope-local: other
  procedures are unaffected.
- **Class / record field prefix** — every field inside a
  `class` / `record` declaration is renamed (e.g. the Delphi convention
  `FData`). References to the field from methods elsewhere in the unit
  are updated consistently.
- **Type-based prefix** — define rules like *"any variable whose type
  matches `TButton` gets the prefix `btn`"*. Patterns are regular
  expressions, so `TList.*` covers `TListBox`, `TListView`, and so on.
  When a variable matches both a scope rule and a type rule you choose
  which wins via `conflictResolution`.
- **Spacing** — single space around `:=`, `=`, `<>`, `<=`, `>=`, after
  `,`, optionally no space before `;`.
- **Alignment** — align `:` columns inside `var` sections and `=` inside
  `const` sections.
- **Whitespace hygiene** — trim trailing whitespace, collapse consecutive
  blank lines, ensure a final newline, normalise `CRLF` ↔ `LF`.
- **Safe by design** — identifier renaming skips member accesses
  (tokens after a `.`), never rewrites inside string literals or
  comments, and never renames a built-in type.
- **Idempotent** — `format(format(x)) == format(x)`.

## Install

Requires Python 3.10 or newer.

```bash
git clone https://github.com/<your-user>/delphi-formatter.git
cd delphi-formatter
pip install -e .
```

Or run without installing:

```bash
PYTHONPATH=src python -m delphi_formatter ...
```

## Quick start

```bash
# Generate a default config file next to your sources
delphi-formatter init-config --output delphi-formatter.json

# Format a single file to stdout
delphi-formatter format MyUnit.pas --config delphi-formatter.json

# ... or in place
delphi-formatter format MyUnit.pas --config delphi-formatter.json --write

# See the diff the formatter would apply
delphi-formatter format MyUnit.pas --config delphi-formatter.json --diff

# Exit 1 if any file would be reformatted (useful in CI / pre-commit)
delphi-formatter check MyUnit.pas --config delphi-formatter.json
```

## Config reference

A default config (from `init-config`):

```json
{
  "indent": {
    "style": "spaces",
    "size": 2,
    "continuationIndent": 2
  },
  "keywords":     { "case": "lower" },
  "builtinTypes": { "case": "preserve" },
  "variablePrefix": {
    "local":      { "enabled": false, "prefix": "L", "capitalizeAfterPrefix": true },
    "classField": { "enabled": false, "prefix": "F", "capitalizeAfterPrefix": true },
    "byType": {
      "enabled": false,
      "rules": [
        { "typePattern": "TButton",     "prefix": "btn" },
        { "typePattern": "TEdit",       "prefix": "edt" },
        { "typePattern": "TLabel",      "prefix": "lbl" },
        { "typePattern": "TForm",       "prefix": "frm" },
        { "typePattern": "TStringList", "prefix": "sl"  },
        { "typePattern": "TList.*",     "prefix": "lst" }
      ],
      "conflictResolution": "typePrefixOverridesScope"
    }
  },
  "alignment": {
    "alignAssignments": false,
    "alignVarColons":   true,
    "alignConstEquals": true,
    "maxAlignSpaces":   40
  },
  "spacing": {
    "aroundOperators":  true,
    "afterComma":       true,
    "beforeSemicolon":  false,
    "insideParens":     false
  },
  "blankLines": {
    "collapseConsecutive": true,
    "maxConsecutive":      1
  },
  "endOfFile": {
    "trimTrailingWhitespace": true,
    "ensureFinalNewline":     true,
    "lineEnding":             "auto"
  },
  "beginEndStyle": {
    "beginOnNewLine": true
  }
}
```

Only the keys you want to override need to appear in your config — unset
keys inherit from the defaults.

### Prefix recipes

| Goal | Config |
|---|---|
| Uppercase keywords, Delphi-standard `F` fields | `"keywords": { "case": "upper" }`, `"variablePrefix.classField": { "enabled": true, "prefix": "F" }` |
| Hungarian-ish VCL locals (`btnOK`, `edtName`, `lstItems`) | `"variablePrefix.byType": { "enabled": true, "conflictResolution": "typePrefixOverridesScope" }` |
| Every local starts with `L` | `"variablePrefix.local": { "enabled": true, "prefix": "L" }` |
| Keep your own spelling of keywords | `"keywords": { "case": "preserve" }` |

## Example

Input:

```pascal
PROCEDURE TMyForm.DoSomething;
VAR
  counter: Integer;
  message: string;
  mainButton: TButton;
BEGIN
  counter:=0;
  message:='start';
  mainButton.Caption:=message;
END;
```

Output with the default config included in this repo
(`delphi-formatter.json`):

```pascal
procedure TMyForm.DoSomething;
var
  LCounter      : Integer;
  LMessage      : string;
  btnMainButton : TButton;
begin
  LCounter := 0;
  LMessage := 'start';
  btnMainButton.Caption := LMessage;
end;
```

See `examples/input_sample.pas` for a richer example.

## Running the tests

```bash
python -m unittest discover tests
```

## How it works

The formatter is a **token stream rewriter**, not a full parser:

1. A hand-written tokenizer produces a flat list of `Token` objects
   that together cover every byte of the input (including comments and
   whitespace). This makes re-emission straightforward.
2. A lightweight scope analyser finds `procedure` / `function` bodies
   and `class` / `record` type blocks. It pairs `begin`/`end`, tracks
   nested `case` / `try` / `asm` blocks, and skips forward
   declarations.
3. Token-level passes rename identifiers, normalise keyword casing, and
   apply spacing rules.
4. The token stream is re-emitted to text and two text-level passes
   apply column alignment and whitespace hygiene.

See the `src/delphi_formatter/` tree — each pass lives in its own file
under `rules/`.

## Limitations

- No semantic analysis — the formatter doesn't resolve imported
  symbols, so cross-unit references aren't renamed. Fields of a class
  defined in this unit *are* renamed unit-wide.
- Compiler-directive conditionals (`{$IFDEF}` ... `{$ENDIF}`) are
  preserved verbatim; asymmetric code inside different branches is
  handled naïvely.
- Indentation rewriting is deliberately conservative — existing
  indentation is preserved; only alignment within `var` / `const`
  blocks is adjusted.

## License

MIT.

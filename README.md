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
  `String`, `Boolean`, `TDateTime`. Supports an extra `match-keywords`
  value that keeps built-in types in lock-step with whatever you picked
  for `keywords.case` (so `string` stays lower when `begin` does, and
  `STRING` when `BEGIN` does). **Per-type overrides** let you pin the
  exact spelling of individual types (e.g. keep `string` lowercase but
  force `Integer`, `Boolean`, `TDateTime` with a capital initial).
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
- **Spacing** — fine-grained control: dedicated options for the
  assignment operator `:=` (`num := 5`) and for the declaration colon
  `:` (`num: Integer`), each with independent *before* / *after* toggles,
  plus a master switch for other binary operators, `,` and `;`.
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

# ... or build one interactively (recommended: walks you through every option)
delphi-formatter wizard --output delphi-formatter.json

# Format a single file to stdout
delphi-formatter format MyUnit.pas --config delphi-formatter.json

# ... or in place
delphi-formatter format MyUnit.pas --config delphi-formatter.json --write

# See the diff the formatter would apply
delphi-formatter format MyUnit.pas --config delphi-formatter.json --diff

# Exit 1 if any file would be reformatted (useful in CI / pre-commit)
delphi-formatter check MyUnit.pas --config delphi-formatter.json
```

## Interactive setup (`wizard`)

If you don't want to read the whole config reference below, run the wizard
and let it guide you:

```bash
delphi-formatter wizard --output delphi-formatter.json
```

What you get:

1. **Starting profile** — pick one of:
   - **Minimal** — everything off (pure defaults)
   - **Delphi-standard** — lower-case keywords, `F` class-field prefix
   - **VCL Hungarian** — `L` locals, `F` fields, type-based rules on
     (`btn`, `edt`, `lbl`, …)
   - or start **from an existing config** via `--from my-config.json`
2. **Section-by-section refinement** — menu of ten sections: indentation,
   keyword/built-in case, local/field prefix, spacing, alignment, blank
   lines, line endings, plus a dedicated entry for the
   **`byType` rules sub-loop**.
3. **`byType` sub-loop** — add / edit / remove `typePattern → prefix` pairs
   one at a time (e.g. `TCheckBox → chk`). Regex patterns are validated
   before acceptance, and prefixes must be valid Pascal identifiers.
4. **Preview on sample** — at any point, pick `Preview on sample` and the
   wizard reformats an embedded Delphi snippet with the *current* config,
   so you can see the effect of your choices before saving.
5. **Validate & save** — the final config passes through
   `validate_config()` before being written.

Pass `--force` to overwrite an existing output file without being asked.

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
  "builtinTypes": { "case": "preserve", "overrides": {} },
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
    "insideParens":     false,
    "assignment": {
      "spaceBefore": true,
      "spaceAfter":  true
    },
    "declarationColon": {
      "spaceBefore": false,
      "spaceAfter":  true
    }
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

`keywords.case` accepts `"lower"`, `"upper"`, or `"preserve"`.
`builtinTypes.case` accepts those three values **plus** `"match-keywords"`,
which is a shortcut meaning *"use whatever `keywords.case` is set to"*.

`builtinTypes.overrides` takes precedence over `builtinTypes.case` on a
per-type basis. Keys are matched case-insensitively; values are the
literal spelling to emit (and must spell the same identifier as the key).
Typical idiomatic-Delphi recipe:

```json
"builtinTypes": {
  "case": "lower",
  "overrides": {
    "Integer":   "Integer",
    "Boolean":   "Boolean",
    "TDateTime": "TDateTime",
    "Cardinal":  "Cardinal"
  }
}
```

…gives you lowercase `string`, `char`, `real`, etc. but keeps `Integer`,
`Boolean`, `TDateTime`, `Cardinal` with their conventional capital initial.

### Prefix recipes

| Goal | Config |
|---|---|
| Uppercase keywords, Delphi-standard `F` fields | `"keywords": { "case": "upper" }`, `"variablePrefix.classField": { "enabled": true, "prefix": "F" }` |
| Hungarian-ish VCL locals (`btnOK`, `edtName`, `lstItems`) | `"variablePrefix.byType": { "enabled": true, "conflictResolution": "typePrefixOverridesScope" }` |
| Every local starts with `L` | `"variablePrefix.local": { "enabled": true, "prefix": "L" }` |
| Keep your own spelling of keywords | `"keywords": { "case": "preserve" }` |
| Lowercase everything (keywords *and* `Integer`, `Boolean`, `TDateTime`, …) | `"keywords": { "case": "lower" }`, `"builtinTypes": { "case": "match-keywords" }` |
| Same, but UPPERCASE | `"keywords": { "case": "upper" }`, `"builtinTypes": { "case": "match-keywords" }` |
| Lowercase `string`/`char`/`real` but capital `Integer`/`Boolean`/`TDateTime` | `"builtinTypes": { "case": "lower", "overrides": { "Integer": "Integer", "Boolean": "Boolean", "TDateTime": "TDateTime" } }` |
| Tight declarations, loose assignments (`num:Integer` and `num := 5`) | `"spacing.declarationColon": { "spaceBefore": false, "spaceAfter": false }` + default `assignment` |
| Roomy declarations (`num : Integer`) | `"spacing.declarationColon": { "spaceBefore": true, "spaceAfter": true }` |
| No spaces at all around `:=` (`num:=5`) | `"spacing.assignment": { "spaceBefore": false, "spaceAfter": false }` |

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

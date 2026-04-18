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
  `STRING` when `BEGIN` does).
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

## Formatting a whole project

`format` and `check` both accept **one or more files or directories**.
When you pass a directory the formatter walks it recursively, applies the
include / exclude filters, and processes every source file that matches.

```bash
# See what would change across the whole tree (no writes, exit 1 if dirty)
delphi-formatter format src/ --config delphi-formatter.json --check

# Reformat the whole project in place
delphi-formatter format src/ --config delphi-formatter.json --write

# Preview the diff for a multi-root tree
delphi-formatter format src/ tests/ --config delphi-formatter.json --diff | less

# Include .dpr and .dpk on top of the default *.pas, skip a legacy subtree
delphi-formatter format src/ --config delphi-formatter.json --write \
    --include "*.pas" --include "*.dpr" --include "*.dpk" \
    --exclude "src/legacy/**"
```

Rules to remember:

- On a directory (or multiple paths) one of `--write`, `--diff`, `--check`
  is **required** — no accidental mass reformatting.
- Default includes: `*.pas` (override with one or more `--include GLOB`).
- Default excludes: `**/bin/**`, `**/obj/**`, `**/__history/**`,
  `**/__recovery/**` (Delphi/IDE build output). Your `--exclude`s are
  *added* on top; use `--no-default-excludes` to start from a clean slate.
- Use `--quiet` to suppress per-file output (summary and errors only) or
  `--verbose` to print one line per file, changed or not.
- `check` is a convenience alias for `format --check`.
- Per-file errors (decode failure, formatter error, …) never abort the
  run. They're collected into the final summary; the exit code is `1` if
  any file errored.

Exit codes:

| Code | Meaning                                                         |
|------|-----------------------------------------------------------------|
| 0    | clean — nothing to change (check) or every file written (write) |
| 1    | at least one file would change (check) **or** a per-file error  |
| 2    | config error, bad usage, missing path, or missing mode flag     |

### CI / pre-commit

```yaml
# GitHub Action snippet
- run: pip install -e .
- run: delphi-formatter format src/ --config delphi-formatter.json --check
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

### Prefix recipes

| Goal | Config |
|---|---|
| Uppercase keywords, Delphi-standard `F` fields | `"keywords": { "case": "upper" }`, `"variablePrefix.classField": { "enabled": true, "prefix": "F" }` |
| Hungarian-ish VCL locals (`btnOK`, `edtName`, `lstItems`) | `"variablePrefix.byType": { "enabled": true, "conflictResolution": "typePrefixOverridesScope" }` |
| Every local starts with `L` | `"variablePrefix.local": { "enabled": true, "prefix": "L" }` |
| Keep your own spelling of keywords | `"keywords": { "case": "preserve" }` |
| Lowercase everything (keywords *and* `Integer`, `Boolean`, `TDateTime`, …) | `"keywords": { "case": "lower" }`, `"builtinTypes": { "case": "match-keywords" }` |
| Same, but UPPERCASE | `"keywords": { "case": "upper" }`, `"builtinTypes": { "case": "match-keywords" }` |
| Tight declarations, loose assignments (`num:Integer` and `num := 5`) | `"spacing.declarationColon": { "spaceBefore": false, "spaceAfter": false }` + default `assignment` |
| Roomy declarations (`num : Integer`) | `"spacing.declarationColon": { "spaceBefore": true, "spaceAfter": true }` |
| No spaces at all around `:=` (`num:=5`) | `"spacing.assignment": { "spaceBefore": false, "spaceAfter": false }` |

## VCL forms and DFM files

In a VCL / FMX project the `.pas` file of a form is paired with a sibling
`.dfm` (or `.fmx`) resource. The DFM declares every visual component by
name:

```
object Form1: TForm1
  object Button1: TButton
    OnClick = Button1Click
  end
end
```

The name `Button1` in the DFM **must** match the field `Button1` declared
in the form class. Renaming one without the other silently breaks the
visual binding — the component simply stops working at runtime.

To keep you safe, the formatter detects *form classes* (classes that
inherit from `TForm`, `TFrame`, `TDataModule` or `TCustomForm`, or whose
`.pas` has a sibling `.dfm`) and treats them specially.

### `variablePrefix.skipVisualComponents`

This boolean controls what happens when a rename rule would touch a form
field.

- **`true` (default, recommended)** — form classes are left alone. Their
  fields are never renamed and their `.dfm` is never touched. Non-form
  classes still get the full rename treatment. This is the safe choice if
  you've just dropped the formatter into an existing project.

- **`false`** — the formatter renames form fields **and** patches the
  sibling `.dfm` in sync. Every occurrence of the old field name in the
  DFM (in `object <Name>: <Type>` headers, and in bare-identifier property
  values like `DataSource = DataSource1`) is rewritten. Event handler
  properties (`OnClick`, `OnChange`, `Columns.OnColumnClick`, …) are
  never renamed — they point at methods, which the formatter doesn't
  touch.

Example with `skipVisualComponents: false` and a `byType` rule
`TButton → btn`:

```
# before
Unit1.pas:   Button1: TButton;
Unit1.dfm:   object Button1: TButton ... end

# after `delphi-formatter format Unit1.pas --write`
Unit1.pas:   btnButton1: TButton;
Unit1.dfm:   object btnButton1: TButton ... end
```

The DFM is rewritten **positionally** — indentation, comments, blank
lines, CRLF line endings, binary picture blocks, and everything else that
isn't the renamed identifier stays byte-identical.

### Binary DFMs

Delphi can save DFMs in either textual (default) or binary form (magic
bytes `TPF0`). The formatter only handles textual DFMs. If it encounters
a binary DFM it refuses the pair cleanly — the `.pas` is left untouched
and a `error: ... dfm is in binary format, convert to text first` line
is printed on stderr. Convert the DFM to text in Delphi's IDE (right
click → *View as Text*) before running the formatter.

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

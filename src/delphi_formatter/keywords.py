"""Delphi / Object Pascal reserved words, directives and common built-in types.

Delphi is case-insensitive for identifiers and keywords, so matching is done
by comparing lowercased forms. Sets below are stored lowercase.
"""

# Reserved words (keywords that cannot be used as identifiers).
RESERVED_WORDS: frozenset[str] = frozenset({
    "and", "array", "as", "asm", "begin", "case", "class", "const",
    "constructor", "destructor", "dispinterface", "div", "do", "downto",
    "else", "end", "except", "exports", "file", "finalization", "finally",
    "for", "function", "goto", "if", "implementation", "in", "inherited",
    "initialization", "inline", "interface", "is", "label", "library",
    "mod", "nil", "not", "object", "of", "or", "out", "packed", "procedure",
    "program", "property", "raise", "record", "repeat", "resourcestring",
    "set", "shl", "shr", "string", "then", "threadvar", "to", "try", "type",
    "unit", "until", "uses", "var", "while", "with", "xor",
    # Common Delphi-specific
    "private", "protected", "public", "published", "automated", "strict",
    "true", "false",
})

# Directives / contextual keywords — not reserved but usually colored.
DIRECTIVES: frozenset[str] = frozenset({
    "absolute", "abstract", "assembler", "cdecl", "contains", "default",
    "delayed", "deprecated", "dispid", "dynamic", "experimental", "export",
    "external", "far", "final", "forward", "helper", "implements", "index",
    "local", "message", "name", "near", "nodefault", "overload", "override",
    "package", "pascal", "platform", "read", "readonly", "reference",
    "register", "reintroduce", "requires", "resident", "safecall", "sealed",
    "static", "stdcall", "stored", "unsafe", "varargs", "virtual", "write",
    "writeonly", "winapi",
})

# Built-in simple/generic types with their canonical (RTL-documented)
# spelling. Used by ``builtinTypes.case = "canonical"`` to render each type
# in the form the Embarcadero docs use, *regardless* of how the author
# originally wrote it. Keys are lowercased for O(1) case-insensitive lookup.
BUILTIN_TYPES_CANONICAL: dict[str, str] = {
    "integer":       "Integer",
    "cardinal":      "Cardinal",
    "shortint":      "ShortInt",
    "smallint":      "SmallInt",
    "longint":       "LongInt",
    "int64":         "Int64",
    "uint64":        "UInt64",
    "byte":          "Byte",
    "word":          "Word",
    "longword":      "LongWord",
    "nativeint":     "NativeInt",
    "nativeuint":    "NativeUInt",
    "single":        "Single",
    "double":        "Double",
    "extended":      "Extended",
    "real":          "Real",
    "real48":        "Real48",
    "currency":      "Currency",
    "comp":          "Comp",
    "boolean":       "Boolean",
    "bytebool":      "ByteBool",
    "wordbool":      "WordBool",
    "longbool":      "LongBool",
    "char":          "Char",
    "ansichar":      "AnsiChar",
    "widechar":      "WideChar",
    "string":        "String",
    "ansistring":    "AnsiString",
    "widestring":    "WideString",
    "unicodestring": "UnicodeString",
    "shortstring":   "ShortString",
    "pchar":         "PChar",
    "pansichar":     "PAnsiChar",
    "pwidechar":     "PWideChar",
    "pointer":       "Pointer",
    "variant":       "Variant",
    "olevariant":    "OleVariant",
    "tdatetime":     "TDateTime",
    "tdate":         "TDate",
    "ttime":         "TTime",
    "tobject":       "TObject",
}

# Built-in simple/generic types — case policy configurable separately.
BUILTIN_TYPES: frozenset[str] = frozenset(BUILTIN_TYPES_CANONICAL.keys())

# Words that, when used as the *type* in a variable declaration, should be
# left untouched by the identifier-rename pass even if they happen to match
# configured prefix rules. (Safety net — the tokenizer gives us the position
# anyway.)
TYPE_LIKE: frozenset[str] = BUILTIN_TYPES | {
    "tbutton", "tedit", "tlabel", "tform", "tmemo", "tlist", "tstringlist",
    "tcombobox", "tcheckbox", "tradiobutton", "tpanel", "tpagecontrol",
    "ttabsheet", "tdatasource", "tdataset", "tquery", "ttable",
}


def is_keyword(word: str) -> bool:
    """True if *word* is a reserved word (case-insensitive)."""
    return word.lower() in RESERVED_WORDS


def is_directive(word: str) -> bool:
    return word.lower() in DIRECTIVES


def is_builtin_type(word: str) -> bool:
    return word.lower() in BUILTIN_TYPES


def canonical_builtin_spelling(word: str) -> str | None:
    """Return the canonical RTL spelling of *word*, or None if unknown."""
    return BUILTIN_TYPES_CANONICAL.get(word.lower())


def is_keyword_or_directive(word: str) -> bool:
    w = word.lower()
    return w in RESERVED_WORDS or w in DIRECTIVES

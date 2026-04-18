"""Top-level formatter pipeline.

Call :func:`format_source` with the raw Delphi source and a config dict (as
returned by :func:`delphi_formatter.config.load_config`).

Pipeline order:

1. Tokenise
2. Token-level passes:
    a. keyword case
    b. identifier prefix rename (scope-aware)
    c. spacing around operators / after commas
3. Re-emit to text
4. Text-level passes:
    a. var/const column alignment
    b. whitespace normalisation (trim trailing, blank lines, final newline, line endings)
"""

from __future__ import annotations

from typing import Any

from .tokenizer import detokenize, tokenize
from .rules import alignment, identifier_prefix, keyword_case, spacing, whitespace


def format_source(source: str, config: dict[str, Any]) -> str:
    tokens = tokenize(source)

    # Token-level passes (order matters: rename first so case rules see final kw state)
    identifier_prefix.apply(tokens, config)
    keyword_case.apply(tokens, config)
    spacing.apply(tokens, config)

    text = detokenize(tokens)

    # Text-level passes
    text = alignment.apply(text, config)
    text = whitespace.apply(text, config)

    return text

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

For VCL forms, use :func:`format_pas_with_dfm` instead of calling this
directly — it orchestrates the field rename map between the ``.pas`` and
its sibling ``.dfm`` so the visual binding stays consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import dfm as dfm_mod
from .tokenizer import detokenize, tokenize
from .rules import alignment, identifier_prefix, keyword_case, spacing, whitespace


# ---------------------------------------------------------------------------
# Reports + pair-result containers
# ---------------------------------------------------------------------------


@dataclass
class FormatReport:
    """What the formatter did, when the caller asked for details.

    ``field_rename_map`` is the unit-wide rename map applied to class fields
    (the only renames that propagate to a sibling ``.dfm``). Locals never
    cross procedure boundaries and so never appear here.
    """
    field_rename_map: dict[str, str] = field(default_factory=dict)


@dataclass
class PairResult:
    """Outcome of :func:`format_pas_with_dfm`.

    ``dfm_text_after`` is None when there was no sibling DFM, or when the
    DFM was given but didn't need any edit. ``dfm_error`` carries a short
    message when the DFM couldn't be processed (e.g. binary format); in
    that case the ``.pas`` is left untouched to keep the pair atomic.
    """
    pas_text_after: str
    dfm_text_after: str | None
    report: FormatReport
    dfm_error: str | None = None


# ---------------------------------------------------------------------------
# Core entry point
# ---------------------------------------------------------------------------


def format_source(
    source: str,
    config: dict[str, Any],
    *,
    has_dfm_sibling: bool = False,
    return_report: bool = False,
) -> Any:
    """Format a single Delphi source string.

    With no keyword-only arguments, returns a plain ``str`` — unchanged
    from the original public API. Callers who need the rename map (mainly
    :func:`format_pas_with_dfm`) pass ``return_report=True`` and get back
    a ``tuple[str, FormatReport]``.
    """
    tokens = tokenize(source)

    # Token-level passes (order matters: rename first so case rules see
    # final kw state).
    field_rename_map = identifier_prefix.apply(
        tokens, config, has_dfm_sibling=has_dfm_sibling
    ) or {}
    keyword_case.apply(tokens, config)
    spacing.apply(tokens, config)

    text = detokenize(tokens)

    # Text-level passes
    text = alignment.apply(text, config)
    text = whitespace.apply(text, config)

    if return_report:
        return text, FormatReport(field_rename_map=field_rename_map)
    return text


# ---------------------------------------------------------------------------
# High-level PAS + DFM orchestration
# ---------------------------------------------------------------------------


def format_pas_with_dfm(
    pas_text: str,
    dfm_text: str | None,
    config: dict[str, Any],
) -> PairResult:
    """Format a ``.pas`` and, if given, keep the sibling ``.dfm`` in sync.

    When the rename rules produce a non-empty field rename map, the DFM is
    parsed and the same rename is applied to ``object Name: Type`` headers
    and bare-identifier property values (but never to ``On*`` event
    handlers, which point at methods). If there's nothing to rename in the
    DFM, ``dfm_text_after`` is None.

    If ``dfm_text`` is given but is a binary DFM (magic ``TPF0``), or if
    parsing fails in some unrecoverable way, the ``.pas`` is NOT formatted
    and ``dfm_error`` is set — the pair is atomic by design.
    """
    has_dfm = dfm_text is not None

    # Early-refuse binary DFMs before we touch the pas.
    if has_dfm and dfm_text is not None:
        # Cheap encoded-form check: only a real binary file would begin with
        # the magic bytes, and our caller is expected to hand us decoded
        # text. But if the caller decoded UTF-8 from a binary blob the
        # conversion would have raised; getting here with 'TPF0' at the
        # start is unlikely but we still handle it.
        head = dfm_text[:4].encode("latin-1", errors="ignore")
        if dfm_mod.is_binary_dfm(head):
            return PairResult(
                pas_text_after=pas_text,
                dfm_text_after=None,
                report=FormatReport(),
                dfm_error="dfm is in binary format, convert to text first",
            )

    pas_after, report = format_source(
        pas_text,
        config,
        has_dfm_sibling=has_dfm,
        return_report=True,
    )

    dfm_after: str | None = None
    if has_dfm and dfm_text is not None and report.field_rename_map:
        try:
            root = dfm_mod.parse_dfm(dfm_text)
        except dfm_mod.DfmParseError as exc:
            # Don't fail the whole pair — just report the parse error.
            return PairResult(
                pas_text_after=pas_after,
                dfm_text_after=None,
                report=report,
                dfm_error=f"dfm parse error: {exc}",
            )
        new_dfm = dfm_mod.apply_rename(dfm_text, root, report.field_rename_map)
        if new_dfm != dfm_text:
            dfm_after = new_dfm

    return PairResult(
        pas_text_after=pas_after,
        dfm_text_after=dfm_after,
        report=report,
        dfm_error=None,
    )

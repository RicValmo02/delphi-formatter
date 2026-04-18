"""Directory-aware driver for the Delphi formatter.

Everything that isn't argparse plumbing lives here: file discovery,
include/exclude filtering, per-file formatting, diff generation, result
aggregation. The CLI (`cli.py`) is a thin layer on top that parses flags
and calls :func:`run`.

Keeping this logic out of ``cli.py`` means we can test discovery and
the driver in isolation without subprocessing the CLI.
"""

from __future__ import annotations

import difflib
import fnmatch
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, TextIO

from . import dfm as dfm_mod
from .formatter import format_pas_with_dfm, format_source


# ---------------------------------------------------------------------------
# Modes and defaults
# ---------------------------------------------------------------------------


class Mode(Enum):
    """How :func:`run` should report / apply the formatted output."""

    STDOUT = "stdout"   # print to stdout - only valid for a single input file
    WRITE = "write"     # overwrite each input file in place
    DIFF = "diff"       # emit unified diffs on stdout, don't touch files
    CHECK = "check"     # report what would change, exit non-zero if any


class Verbosity(Enum):
    NORMAL = "normal"   # print per-file lines only when something happens
    QUIET = "quiet"     # print only the final summary and errors
    VERBOSE = "verbose" # print one line per file, changed or not


DEFAULT_INCLUDES: tuple[str, ...] = ("*.pas",)
DEFAULT_EXCLUDES: tuple[str, ...] = (
    "**/bin/**",
    "**/obj/**",
    "**/__history/**",
    "**/__recovery/**",
)


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------


@dataclass
class FileResult:
    """Outcome of processing a single file (possibly paired with a ``.dfm``)."""

    path: Path
    changed: bool = False            # True if formatter output != input
    written: bool = False            # True if we actually rewrote the file
    error: str | None = None         # short message if something failed
    diff: str | None = None          # unified diff, only populated in DIFF mode

    # Paired ``.dfm`` sibling — populated only for form-class .pas files when
    # ``skipVisualComponents`` is False. ``sibling_path`` is set as soon as
    # the runner locates a DFM next to the PAS (even if nothing changes in
    # it); ``sibling_changed`` / ``sibling_written`` / ``sibling_diff``
    # follow the same semantics as the top-level fields.
    sibling_path: Path | None = None
    sibling_changed: bool = False
    sibling_written: bool = False
    sibling_diff: str | None = None


@dataclass
class RunSummary:
    results: list[FileResult] = field(default_factory=list)

    @property
    def n_total(self) -> int:
        return len(self.results)

    @property
    def n_changed(self) -> int:
        return sum(1 for r in self.results if r.changed and r.error is None)

    @property
    def n_written(self) -> int:
        return sum(1 for r in self.results if r.written)

    @property
    def n_errors(self) -> int:
        return sum(1 for r in self.results if r.error is not None)

    @property
    def n_unchanged(self) -> int:
        return self.n_total - self.n_changed - self.n_errors

    def exit_code(self, mode: Mode) -> int:
        """Standard exit code: 0 clean, 1 if any change/error worth flagging."""
        if self.n_errors:
            return 1
        if mode is Mode.CHECK and self.n_changed:
            return 1
        return 0


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _match_any(path: PurePosixPath, patterns: Iterable[str]) -> bool:
    """True if *path* matches any of the glob *patterns* (fnmatch semantics).

    We match against both the full posix path string AND the basename, so
    ``*.pas`` works for include without the user needing ``**/*.pas``.

    Patterns starting with ``**/`` are also checked with that prefix
    stripped, so ``**/bin/**`` also catches a top-level ``bin/`` directory
    (fnmatch alone would require at least one component before ``bin/``).
    """
    name = path.name
    full = str(path)
    for pat in patterns:
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(full, pat):
            return True
        if pat.startswith("**/") and fnmatch.fnmatch(full, pat[3:]):
            return True
    return False


def iter_source_files(
    roots: list[Path],
    *,
    includes: tuple[str, ...] = DEFAULT_INCLUDES,
    excludes: tuple[str, ...] = DEFAULT_EXCLUDES,
) -> list[Path]:
    """Return a sorted, de-duplicated list of files found under *roots*.

    Each root may be a file or a directory. Files are yielded as-is if they
    exist; directories are walked recursively. Include patterns filter which
    files are kept; exclude patterns drop matches (checked against the path
    relative to the nearest root, in POSIX form, and against the basename).

    Explicit file paths bypass the *include* filter — if the user pointed at
    a file by name, we respect that even if the extension doesn't match the
    default ``*.pas``. Excludes still apply.
    """
    seen: set[Path] = set()
    out: list[Path] = []

    for root in roots:
        if not root.exists():
            # We don't raise here - the caller decides how to surface missing
            # paths (cli.py treats this as usage error with exit code 2).
            raise FileNotFoundError(f"path does not exist: {root}")

        root_abs = root.resolve()

        if root.is_file():
            rel = PurePosixPath(root.name)
            if _match_any(rel, excludes):
                continue
            if root_abs not in seen:
                seen.add(root_abs)
                out.append(root)
            continue

        # Directory: walk recursively.
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                rel = PurePosixPath(path.resolve().relative_to(root_abs).as_posix())
            except ValueError:
                # path.resolve() landed outside the root (e.g. symlink). Fall
                # back to the lexical form.
                rel = PurePosixPath(path.as_posix())
            if _match_any(rel, excludes):
                continue
            if not _match_any(rel, includes):
                continue
            path_abs = path.resolve()
            if path_abs in seen:
                continue
            seen.add(path_abs)
            out.append(path)

    # Deterministic output regardless of filesystem ordering.
    out.sort(key=lambda p: str(p.resolve()).lower())
    return out


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------


def _read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_file(path: Path, content: str) -> None:
    # ``newline=""`` so format_source's endOfFile.lineEnding decision is
    # preserved verbatim on write (no Python-side CRLF rewriting).
    path.write_text(content, encoding="utf-8", newline="")


def _make_diff(path: Path, before: str, after: str) -> str:
    """Return a unified diff between *before* and *after* for *path*."""
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=str(path),
        tofile=f"{path} (formatted)",
    ))


def _find_dfm_sibling(pas_path: Path) -> Path | None:
    """Return the sibling ``.dfm`` for *pas_path* if one exists, case-insensitively.

    Windows filesystems are case-insensitive, but POSIX ones aren't; on Linux
    a user might well have ``Form1.pas`` next to ``Form1.DFM``. We try the
    common-case direct path first (cheap), then fall back to a directory
    listing for a case-insensitive match.
    """
    # Fast path: exact ``.dfm`` suffix.
    direct = pas_path.with_suffix(".dfm")
    if direct.is_file():
        return direct

    # Slow path: scan the directory for a case-insensitive match on the
    # basename. We only do this if the fast path missed, so it's cheap in
    # aggregate (most projects use lowercase ``.dfm``).
    stem_lower = pas_path.stem.lower()
    parent = pas_path.parent
    try:
        entries = list(parent.iterdir())
    except OSError:
        return None
    for entry in entries:
        if not entry.is_file():
            continue
        if entry.suffix.lower() != ".dfm":
            continue
        if entry.stem.lower() == stem_lower:
            return entry
    return None


def _read_dfm_maybe_binary(dfm_path: Path) -> tuple[str | None, str | None]:
    """Read a DFM file, detecting binary format.

    Returns ``(text, error)``:

    - ``(text, None)`` — a textual DFM was decoded successfully.
    - ``(None, "...")`` — binary format, I/O error, or decode error. The
      error string is suitable for assignment to ``FileResult.error``.
    """
    try:
        raw = dfm_path.read_bytes()
    except OSError as exc:
        return None, f"dfm read failed: {exc}"
    if dfm_mod.is_binary_dfm(raw):
        return None, "dfm is in binary format, convert to text first"
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return None, f"dfm decode error: {exc.reason}"


def _process_one(path: Path, config: dict[str, Any], mode: Mode) -> FileResult:
    """Format one file and return what happened. Never raises.

    For ``.pas`` files, when ``variablePrefix.skipVisualComponents`` is
    False and a sibling ``.dfm`` exists, the pair is processed atomically:
    any field rename applied in the pas is propagated to the dfm. If the
    dfm can't be processed (binary / decode error / parse error) the pas
    is left untouched to keep the pair consistent.
    """
    # Read the pas source first.
    try:
        before = _read_file(path)
    except UnicodeDecodeError as exc:
        return FileResult(path=path, error=f"decode error: {exc.reason}")
    except OSError as exc:
        return FileResult(path=path, error=f"read failed: {exc}")

    # Decide whether we need to consider a sibling DFM. We only look at
    # siblings for ``.pas`` files when the user has opted into the sync.
    vp = config.get("variablePrefix", {}) or {}
    skip_visual = bool(vp.get("skipVisualComponents", True))
    consider_dfm = (not skip_visual) and path.suffix.lower() == ".pas"

    sibling_path: Path | None = None
    dfm_before: str | None = None

    if consider_dfm:
        sibling_path = _find_dfm_sibling(path)
        if sibling_path is not None:
            dfm_before, dfm_err = _read_dfm_maybe_binary(sibling_path)
            if dfm_err is not None:
                # Binary / decode / I/O: do NOT touch the pas. Report the
                # sibling error on the pair.
                return FileResult(
                    path=path,
                    sibling_path=sibling_path,
                    error=dfm_err,
                )

    # Format the pas (possibly paired with a DFM).
    try:
        if consider_dfm and sibling_path is not None:
            pair = format_pas_with_dfm(before, dfm_before, config)
            if pair.dfm_error is not None:
                return FileResult(
                    path=path,
                    sibling_path=sibling_path,
                    error=pair.dfm_error,
                )
            after = pair.pas_text_after
            dfm_after = pair.dfm_text_after
        else:
            after = format_source(before, config)
            dfm_after = None
    except Exception as exc:  # defensive: formatter bugs shouldn't abort run
        return FileResult(path=path, error=f"format error: {exc}")

    changed = (after != before)
    sibling_changed = dfm_after is not None and dfm_before is not None and dfm_after != dfm_before

    result = FileResult(
        path=path,
        changed=changed or sibling_changed,  # the pair is changed if either side is
        sibling_path=sibling_path,
        sibling_changed=sibling_changed,
    )

    # Nothing to do if nothing changed on either side.
    if not changed and not sibling_changed:
        return result

    if mode is Mode.WRITE:
        # Write pas only if it actually changed.
        if changed:
            try:
                _write_file(path, after)
                result.written = True
            except OSError as exc:
                result.error = f"write failed: {exc}"
                return result
        # Write sibling dfm only if it actually changed.
        if sibling_changed and sibling_path is not None and dfm_after is not None:
            try:
                _write_file(sibling_path, dfm_after)
                result.sibling_written = True
            except OSError as exc:
                result.error = f"dfm write failed: {exc}"
                return result
        return result

    if mode is Mode.DIFF:
        if changed:
            result.diff = _make_diff(path, before, after)
        if sibling_changed and sibling_path is not None and dfm_before is not None and dfm_after is not None:
            result.sibling_diff = _make_diff(sibling_path, dfm_before, dfm_after)
        return result

    if mode is Mode.STDOUT:
        # Single-file stdout mode: we only emit the pas payload. Pairs
        # shouldn't normally happen in STDOUT mode (the CLI enforces a
        # single-file argument), but guard defensively.
        result.diff = after
        return result

    # Mode.CHECK: nothing else to do, just report.
    return result


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------


def _emit_file_line(
    out: TextIO,
    result: FileResult,
    mode: Mode,
    verbosity: Verbosity,
) -> None:
    """Per-file status line to stderr-ish stream (not used for DIFF payload)."""
    if verbosity is Verbosity.QUIET:
        return
    if result.error is not None:
        out.write(f"error: {result.path}: {result.error}\n")
        return
    if result.changed:
        # Primary pas line.
        if mode is Mode.WRITE:
            if result.written:
                out.write(f"formatted: {result.path}\n")
            elif result.sibling_written:
                # pas unchanged but sibling dfm was rewritten — surface the pair
                out.write(f"formatted (dfm only): {result.path}\n")
        elif mode is Mode.CHECK:
            out.write(f"would reformat: {result.path}\n")
        # Extra sibling line when the dfm was part of the change.
        if result.sibling_changed and result.sibling_path is not None:
            if mode is Mode.WRITE and result.sibling_written:
                out.write(f"  + sibling: {result.sibling_path}\n")
            elif mode is Mode.CHECK:
                out.write(f"  + sibling: {result.sibling_path}\n")
        # Mode.DIFF / Mode.STDOUT print the payload itself elsewhere.
        return
    if verbosity is Verbosity.VERBOSE:
        out.write(f"unchanged: {result.path}\n")


def _emit_summary(out: TextIO, summary: RunSummary, mode: Mode) -> None:
    """One-line summary at the end of the run."""
    parts = []
    if mode is Mode.WRITE:
        parts.append(f"{summary.n_written} file(s) reformatted")
    elif mode is Mode.CHECK:
        parts.append(f"{summary.n_changed} file(s) would be reformatted")
    elif mode is Mode.DIFF:
        parts.append(f"{summary.n_changed} file(s) with diff")
    parts.append(f"{summary.n_unchanged} file(s) unchanged")
    if summary.n_errors:
        parts.append(f"{summary.n_errors} file(s) with errors")
    out.write(", ".join(parts) + "\n")


def run(
    paths: list[Path],
    config: dict[str, Any],
    mode: Mode,
    *,
    includes: tuple[str, ...] = DEFAULT_INCLUDES,
    excludes: tuple[str, ...] = DEFAULT_EXCLUDES,
    verbosity: Verbosity = Verbosity.NORMAL,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> RunSummary:
    """Discover files under *paths* and format each with *config* in *mode*.

    - ``stdout`` carries the *payload* (diffs in DIFF mode, formatted output
      in STDOUT mode). Nothing else is written there.
    - ``stderr`` carries the *conversation* (per-file status lines, summary,
      errors) so the payload can always be piped cleanly.
    """
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr

    files = iter_source_files(paths, includes=includes, excludes=excludes)

    summary = RunSummary()
    for path in files:
        result = _process_one(path, config, mode)
        summary.results.append(result)

        # Payload to stdout.
        if result.error is None and result.changed:
            if mode is Mode.DIFF:
                if result.diff is not None:
                    stdout.write(result.diff)
                if result.sibling_diff is not None:
                    stdout.write(result.sibling_diff)
            elif mode is Mode.STDOUT and result.diff is not None:
                stdout.write(result.diff)

        # Conversation to stderr.
        _emit_file_line(stderr, result, mode, verbosity)

    # Only emit the summary in multi-file modes; single-file STDOUT keeps its
    # original quiet behaviour so pipelines stay untouched.
    if mode is not Mode.STDOUT and verbosity is not Verbosity.QUIET:
        _emit_summary(stderr, summary, mode)
    elif mode is not Mode.STDOUT and verbosity is Verbosity.QUIET and summary.n_errors:
        # In quiet mode, still surface that there were errors.
        _emit_summary(stderr, summary, mode)

    return summary

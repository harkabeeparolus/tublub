"""Convert tabular information files between different formats using Tablib.

If no outfile is specified the result will be printed to STDOUT instead,
either in the requested output format, or pretty-printed as a table.
"""

import argparse
import csv
import functools
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, TextIO

import tablib
import tablib.formats

from tublub import __version__


class TublubError(ValueError):
    """Raised for tublub-specific errors (bad format, empty data, etc.)."""


class MultiSheetUnsupportedError(TublubError):
    """Raised when a target format cannot hold a multi-sheet workbook.

    A distinct type so the default-mode fallback can catch exactly this
    failure, while every other TublubError — undetectable target format,
    binary-to-terminal refusal — still propagates. Carries the resolved
    target format so the fallback names what was attempted.
    """

    def __init__(self, message: str, target_format: str) -> None:
        """Store the message and the format that could not hold the sheets."""
        super().__init__(message)
        self.target_format = target_format


@dataclass(frozen=True)
class FormatConfig:
    """Per-format configuration for loading, saving, and opening files."""

    binary: bool = False
    load_args: frozenset[str] = frozenset()
    save_args: frozenset[str] = frozenset()
    open_kwargs: dict[str, Any] = field(default_factory=dict)


_MIN_DATABOOK_INPUTS = 2  # 2+ inputs → multi-sheet Databook output
XLSX_TITLE_LIMIT = 31  # XLSX caps worksheet titles at 31 characters
_DASH = Path("-")
_NAME_PREFIX = "name:"  # --sheet prefix forcing title interpretation
_PICK_ONE_HINT = "pick one sheet with --sheet"


# https://tablib.readthedocs.io/en/stable/formats.html
FORMATS: dict[str, FormatConfig] = {
    "csv": FormatConfig(
        load_args=frozenset(
            {"skip_lines", "headers", "delimiter", "quotechar", "dialect"}
        ),
        save_args=frozenset({"delimiter", "quotechar", "dialect"}),
        open_kwargs={"newline": ""},
    ),
    "tsv": FormatConfig(load_args=frozenset({"skip_lines", "headers"})),
    "xlsx": FormatConfig(binary=True, load_args=frozenset({"skip_lines", "read_only"})),
    "xls": FormatConfig(binary=True, load_args=frozenset({"skip_lines"})),
    "dbf": FormatConfig(binary=True),
    "ods": FormatConfig(binary=True),
    "cli": FormatConfig(save_args=frozenset({"tablefmt"})),
}
_DEFAULT_FMT = FormatConfig()


def cli(
    argv: list[str] | None = None,
    *,
    stderr_isatty: bool | None = None,
    stdin: IO[bytes] | None = None,
) -> int:
    """Run the command line interface (argv defaults to sys.argv).

    stderr_isatty and stdin substitute the two IO edges the single-input
    paths touch, so tests can exercise both cases without patching global
    state; they resolve to the real sys objects deep in the call chain, so
    nothing probes them unless it needs them.
    """
    args, extra_args = parse_command_line(argv)

    if args.list_formats:
        print("Available formats:", " ".join(get_formats()))
        return 0
    if args.list_sheets:
        return _run_list_sheets(args, extra_args, stdin=stdin)
    if args.sheets is not None or args.all_sheets:
        return _run_sheets(args, extra_args, stdin=stdin)
    if len(args.infiles) >= _MIN_DATABOOK_INPUTS:
        return _run_databook(args, extra_args)
    return _run_single(args, extra_args, stderr_isatty=stderr_isatty, stdin=stdin)


def _run_single(
    args: argparse.Namespace,
    extra_args: dict[str, Any],
    *,
    stderr_isatty: bool | None = None,
    stdin: IO[bytes] | None = None,
) -> int:
    """Load one input (file or stdin) with no selection flags and render it."""
    try:
        loaded, source = _load_input(args, extra_args, stdin)
        _render_default(loaded, args, extra_args, source, stderr_isatty=stderr_isatty)
    except TublubError as exc:
        sys.exit(str(exc))

    return 0


def _load_input(
    args: argparse.Namespace,
    extra_args: dict[str, Any],
    stdin: IO[bytes] | None,
) -> tuple[tablib.Databook | tablib.Dataset, str]:
    """Load the one input — file or stdin — and name it for error messages.

    Both sources go through the same try-Databook-then-Dataset handshake, so
    piping a workbook in reads it exactly as a path argument would, whichever
    selection flag asked for it.
    """
    if args.stdin:
        return try_load_stdin(args.in_format, extra_args, stdin=stdin), "stdin"
    path: Path = args.infiles[0]
    loaded = try_load_file(path, extra_args=extra_args, in_format=args.in_format)
    return loaded, str(path)


def _render_default(
    loaded: tablib.Databook | tablib.Dataset,
    args: argparse.Namespace,
    extra_args: dict[str, Any],
    source: str,
    *,
    stderr_isatty: bool | None = None,
) -> None:
    """Render an input that carries no sheet selection.

    A workbook with 2+ sheets converts whole-book under -o/-t (falling back
    to its first sheet when the target cannot hold them all) and otherwise
    prints its first sheet plus a stderr advice line — gated on stderr
    being a terminal, the cheap proxy for "a human is watching", since in a
    pipe it would only be noise. A one-sheet workbook or a fallback Dataset
    renders as a single sheet with no message, exactly as before. A
    Databook is always truthy, so emptiness is asked of sheets() rather
    than of the book. The real sys.stderr is probed at call time, and only
    once there is something to advise.
    """
    if isinstance(loaded, tablib.Dataset):
        if not loaded:
            msg = f"No data was loaded from {source}"
            raise TublubError(msg)
        _render_dataset(loaded, args, extra_args)
        return
    sheets = loaded.sheets()
    if not sheets:
        msg = f"No data was loaded from {source}"
        raise TublubError(msg)
    size = len(sheets)
    if size > 1 and (args.outfile or args.out_format):
        _convert_whole_book(loaded, args, extra_args, source)
        return
    _render_dataset(sheets[0], args, extra_args)
    if size <= 1:
        return
    if stderr_isatty is None:
        stderr_isatty = sys.stderr.isatty()
    if stderr_isatty:
        print(
            f"{source}: {size - 1} more sheet(s) — see -l to list, "
            "-s to pick, --all-sheets for all",
            file=sys.stderr,
        )


def _convert_whole_book(
    book: tablib.Databook,
    args: argparse.Namespace,
    extra_args: dict[str, Any],
    source: str,
) -> None:
    """Convert every sheet, or the first one plus a warning when that fails.

    The default is best-effort: the whole-book attempt carries no --sheet
    hint, and a target that cannot hold several sheets gets the first sheet
    plus an unconditional stderr data-loss warning — dropping data is a
    correctness problem scripts must see, not advice. The warning names -s
    only, never --all-sheets, which errors in this same situation. Only
    MultiSheetUnsupportedError falls back; an undetectable target format,
    an IO error, or a binary-to-terminal refusal still propagates.
    """
    try:
        if args.outfile:
            save_databook_file(
                book,
                file_name=args.outfile,
                force_format=args.out_format,
                extra_args=extra_args,
            )
        else:
            export_databook(book, args.out_format, extra_args)
    except MultiSheetUnsupportedError as exc:
        print(
            f"{source}: format {exc.target_format!r} cannot hold all "
            f"{book.size} sheets; converting only the first (use -s to choose)",
            file=sys.stderr,
        )
        _render_dataset(book.sheets()[0], args, extra_args)


def _render_dataset(
    data: tablib.Dataset, args: argparse.Namespace, extra_args: dict[str, Any]
) -> None:
    """Render one dataset through the output mode selected by args.

    Save to -o, export via -t, or print as a table — the shared tail of
    every single-sheet code path.
    """
    if args.outfile:
        save_dataset_file(
            data,
            file_name=args.outfile,
            force_format=args.out_format,
            extra_args=extra_args,
        )
    elif args.out_format:
        export_dataset(data, args.out_format, extra_args=extra_args)
    else:
        print(_format_dataset_as_table(data, extra_args))


def _format_dataset_as_table(data: tablib.Dataset, extra_args: dict[str, Any]) -> str:
    """Format a dataset for terminal printing, honouring --tablefmt.

    Uses the same "cli" export as -t cli, so printing and converting to
    cli render identically; the style comes from tablib/tabulate unless
    --tablefmt asks for another one. Tablib only registers the cli format
    when tabulate is importable, so an install without it falls back to
    tablib's own built-in table rather than failing.
    """
    if "cli" in get_formats():
        return data.export("cli", **filter_args("save", extra_args, "cli"))
    return str(data)


def _run_list_sheets(
    args: argparse.Namespace,
    extra_args: dict[str, Any],
    *,
    stdin: IO[bytes] | None = None,
) -> int:
    """Print one line per sheet in the input (title, rows, cols)."""
    try:
        loaded, _ = _load_input(args, extra_args, stdin)
    except TublubError as exc:
        sys.exit(str(exc))
    if isinstance(loaded, tablib.Databook):
        for idx, sheet in enumerate(loaded.sheets()):
            ncols = len(sheet.headers or [])
            print(f"[{idx}] {sheet.title}  {len(sheet)} rows x {ncols} cols")
    else:
        # No sheet structure: one bare line, no [idx]/title — nothing to select.
        ncols = len(loaded.headers or [])
        print(f"{len(loaded)} rows x {ncols} cols")
    return 0


def _run_sheets(
    args: argparse.Namespace,
    extra_args: dict[str, Any],
    *,
    stdin: IO[bytes] | None = None,
) -> int:
    """Select sheets with --sheet/--all-sheets from one input and render them."""
    try:
        loaded, source = _load_input(args, extra_args, stdin)
        _render_selection(loaded, args, extra_args, source=source)
    except TublubError as exc:
        sys.exit(str(exc))
    return 0


def _render_selection(
    loaded: tablib.Databook | tablib.Dataset,
    args: argparse.Namespace,
    extra_args: dict[str, Any],
    source: str,
) -> None:
    """Resolve the sheet selection on a loaded input and render the result.

    One selected sheet renders exactly like a single-sheet input; several
    render as a multi-sheet subset. --all-sheets names no specific
    structure, so on an input without sheet structure it is the identity
    modifier: a plain single render, matching _run_single.
    """
    if isinstance(loaded, tablib.Dataset):
        if args.sheets is not None:
            msg = "input has no sheet structure"
            raise TublubError(msg)
        if not loaded:
            msg = f"No data was loaded from {source}"
            raise TublubError(msg)
        _render_dataset(loaded, args, extra_args)
        return
    sheets = loaded.sheets()
    if not sheets:
        msg = "workbook has no sheets"
        raise TublubError(msg)
    if args.all_sheets:
        indices = list(range(len(sheets)))
    else:
        indices = _resolve_sheet_tokens(sheets, args.sheets)
    if len(indices) == 1:
        _render_dataset(sheets[indices[0]], args, extra_args)
    else:
        _render_databook(_databook_subset(sheets, indices), args, extra_args)


def _resolve_sheet_tokens(sheets: list[tablib.Dataset], tokens: list[str]) -> list[int]:
    """Resolve selector tokens to sheet indices; dedup keeps first occurrence."""
    return list(dict.fromkeys(_resolve_one_token(sheets, t) for t in tokens))


def _resolve_one_token(sheets: list[tablib.Dataset], token: str) -> int:
    """Resolve one selector token: name:-forced title, index, or title."""
    if token.startswith(_NAME_PREFIX):
        # Strip exactly one prefix; "name:name:X" selects the literal "name:X".
        return _match_title(sheets, token.removeprefix(_NAME_PREFIX))
    if _is_int_token(token):
        return _resolve_index(sheets, token)
    return _match_title(sheets, token)


def _resolve_index(sheets: list[tablib.Dataset], token: str) -> int:
    """Resolve an integer token as a 0-based sheet index (never as a title)."""
    idx = int(token)
    if 0 <= idx < len(sheets):
        return idx
    msg = f"sheet index {idx} out of range (0-{len(sheets) - 1})"
    if any(sheet.title == token for sheet in sheets):
        msg += f"; for the sheet titled '{token}' use --sheet name:{token}"
    raise TublubError(msg)


def _match_title(sheets: list[tablib.Dataset], wanted: str) -> int:
    """Match a title exactly, then case-insensitively; ambiguity is an error.

    Sheets with empty titles are unmatchable by title (index selection
    still reaches them).
    """
    titled = [
        (idx, title) for idx, sheet in enumerate(sheets) if (title := sheet.title)
    ]
    exact = [idx for idx, title in titled if title == wanted]
    hits = exact or [idx for idx, title in titled if title.lower() == wanted.lower()]
    if len(hits) == 1:
        return hits[0]
    if hits:
        listing = ", ".join(f"[{idx}] '{sheets[idx].title}'" for idx in hits)
        msg = f"sheet title '{wanted}' is ambiguous: matches {listing}; select by index"
        raise TublubError(msg)
    raise TublubError(_no_title_match_msg(wanted, titled))


def _no_title_match_msg(wanted: str, titled: list[tuple[int, str]]) -> str:
    """Compose the no-such-title error, listing what is selectable."""
    titles = ", ".join(f"'{title}'" for _, title in titled)
    msg = f"no sheet titled '{wanted}'; available titles: {titles}"
    if "," in wanted:
        msg += "; repeat --sheet to select multiple sheets by name"
    return msg


def _databook_subset(
    sheets: list[tablib.Dataset], indices: list[int]
) -> tablib.Databook:
    """Build a Databook holding the given sheets, in the given order.

    Duplicate titles (legal in JSON/YAML books) are kept as-is; XLSX
    writers may rename them on save.
    """
    book = tablib.Databook()
    for idx in indices:
        book.add_sheet(sheets[idx])
    return book


def _render_databook(
    book: tablib.Databook, args: argparse.Namespace, extra_args: dict[str, Any]
) -> None:
    """Render a multi-sheet selection through the output mode selected by args.

    Mirrors _render_dataset's save/export/print tail for Databooks.
    """
    if args.outfile:
        save_databook_file(
            book,
            file_name=args.outfile,
            force_format=args.out_format,
            extra_args=extra_args,
            hint=_PICK_ONE_HINT,
        )
    elif args.out_format:
        export_databook(book, args.out_format, extra_args, hint=_PICK_ONE_HINT)
    else:
        print_databook(book, extra_args)


def print_databook(book: tablib.Databook, extra_args: dict[str, Any]) -> None:
    """Print each sheet under a heading, one blank line between sheets."""
    chunks = []
    for sheet in book.sheets():
        heading = f"=== {sheet.title} ({len(sheet)} rows) ==="
        body = _format_dataset_as_table(sheet, extra_args)
        chunks.append(f"{heading}\n{body}" if body else heading)
    print("\n\n".join(chunks))


def _run_databook(args: argparse.Namespace, extra_args: dict[str, Any]) -> int:
    """Build a Databook from multiple inputs and save it."""
    try:
        book = build_databook(
            args.infiles, extra_args=extra_args, in_format=args.in_format
        )
    except TublubError as exc:
        sys.exit(str(exc))
    if book.size == 0:
        sys.exit("No data was loaded from any input file")

    try:
        save_databook_file(
            book,
            file_name=args.outfile,
            force_format=args.out_format,
            extra_args=extra_args,
        )
    except TublubError as exc:
        sys.exit(str(exc))

    return 0


def guess_file_format(filename: Path | None = None) -> str | None:
    """Guess format from file name."""
    if filename and (suf := filename.suffix.lstrip(".")) and suf in get_formats():
        return suf
    return None


def _resolve_output_format(force_format: str | None, file_name: Path) -> str:
    """Resolve output format from an explicit flag or the file extension."""
    file_format = force_format or guess_file_format(file_name)
    if file_format is None:
        msg = f"Unable to detect target file format for: {file_name}"
        raise TublubError(msg)
    return file_format


def _open_for_format(file_name: Path, cfg: FormatConfig, *, write: bool) -> IO[Any]:
    """Open a file in the read/write mode and newline policy its format needs.

    Binary formats open in "rb"/"wb"; everything else in "r"/"w". Only CSV
    sets a non-default newline; it is threaded through here so callers don't
    reach into cfg.open_kwargs at every open site.
    """
    mode = "w" if write else "r"
    if cfg.binary:
        mode += "b"
    return file_name.open(mode, newline=cfg.open_kwargs.get("newline"))


def load_dataset_file(
    file_name: Path,
    extra_args: dict[str, Any],
    in_format: str | None = None,
) -> tablib.Dataset:
    """Load a file into a Tablib dataset."""
    fmt = _resolve_input_format(file_name, in_format)
    cfg = FORMATS.get(fmt, _DEFAULT_FMT)
    extra_load_args = filter_args("load", extra_args, fmt)

    with _open_for_format(file_name, cfg, write=False) as fh:
        return tablib.import_set(fh, format=fmt, **extra_load_args)


def load_databook_file(
    file_name: Path,
    extra_args: dict[str, Any],
    in_format: str | None = None,
) -> tablib.Databook | None:
    """Try to load a file as a multi-sheet Tablib Databook.

    Returns None when the input is not a Databook — either because the
    format doesn't support multi-sheet input at all (csv/tsv/dbf/...) or
    because a Databook-capable format (json/yaml) holds a single-Dataset
    shape (records list rather than [{title, data}, ...]). The caller
    should fall back to load_dataset_file in both cases.

    Mirrors the UnsupportedFormat handling in save_databook_file on the
    export side so we never need a static "which formats support
    import_book" table. KeyError/TypeError are caught alongside it
    because tablib raises those for shape mismatches inside json/yaml.

    Genuine load errors (corrupt files, decode failures) still propagate.
    """
    fmt = _resolve_input_format(file_name, in_format)
    cfg = FORMATS.get(fmt, _DEFAULT_FMT)
    extra_load_args = filter_args("load", extra_args, fmt)

    with _open_for_format(file_name, cfg, write=False) as fh:
        payload = fh.read()
    try:
        return tablib.Databook().load(payload, format=fmt, **extra_load_args)
    except (tablib.UnsupportedFormat, KeyError, TypeError):
        return None


def _resolve_input_format(file_name: Path, in_format: str | None) -> str:
    """Resolve a file's input format and warn on extension/content mismatch.

    Priority: explicit -f flag > content detection > extension.
    We don't trust extensions alone because legacy web exports commonly use
    wrong extensions (e.g. .xls for CSV data). We don't trust detection alone
    because tablib's detect_format() relies on csv.Sniffer, which fails on
    single-column CSV/TSV (no delimiter to sniff). The -f flag is the escape
    hatch for when both fail (e.g. single-column CSV with a .txt extension).
    """
    detected = detect_format_from_file(file_name)
    guessed = guess_file_format(file_name)

    if guessed and detected and guessed != detected:
        print(
            f"Extension suggests {guessed} but content detected as {detected}",
            file=sys.stderr,
        )

    fmt = in_format or detected or guessed
    if fmt is None:
        msg = f"Unable to detect format for: {file_name}"
        raise TublubError(msg)
    return fmt


def detect_format_from_file(file_name: Path) -> str | None:
    """Detect format from file content, independent of file extension."""
    with file_name.open("rb") as fh:
        raw = fh.read()
    return _detect_format_from_bytes(raw)


def _detect_format_from_bytes(raw: bytes) -> str | None:
    """Detect a tablib format from raw bytes, independent of file extension.

    Tablib's detect_format() requires the data in the right form: binary
    formats (xlsx, xls, ods, dbf) need bytes; CSV/TSV need str because
    csv.Sniffer returns None on bytes. JSON and YAML work either way.
    There is no single form that works for all formats, so we try the raw
    bytes first (catches binary formats + json + yaml) then the decoded
    text (csv/tsv).

    As a last resort, if the text looks like plain text lines, assume TSV.
    This catches single-column data where csv.Sniffer fails (no delimiter).
    TSV is preferred over CSV because it won't split on commas in values.
    """
    fmt = tablib.detect_format(raw)
    if fmt is None:
        try:
            text = raw.decode()
        except UnicodeDecodeError:
            return None
        fmt = tablib.detect_format(text)
        if fmt is None and _looks_like_text_lines(text):
            fmt = "tsv"
    return fmt


def load_dataset_stdin(
    in_format: str | None = None,
    extra_args: dict[str, Any] | None = None,
    *,
    stdin: IO[bytes] | None = None,
) -> tablib.Dataset:
    """Load a dataset from stdin (or any injected binary stream)."""
    raw, fmt, extra_load_args = _read_and_detect_stdin(in_format, extra_args, stdin)
    data = raw if is_bin(fmt) else raw.decode()
    return tablib.import_set(data, format=fmt, **extra_load_args)


def load_databook_stdin(
    in_format: str | None = None,
    extra_args: dict[str, Any] | None = None,
    *,
    stdin: IO[bytes] | None = None,
) -> tablib.Databook | None:
    """Try to load a multi-sheet Tablib Databook from stdin.

    Returns None when the input is not a Databook (caller should fall
    back to load_dataset_stdin). Mirrors load_databook_file on the file
    side; see that docstring for the catch policy. Note: stdin can only
    be consumed once, so callers must choose this helper or
    load_dataset_stdin per invocation, not both.
    """
    raw, fmt, extra_load_args = _read_and_detect_stdin(in_format, extra_args, stdin)
    data = raw if is_bin(fmt) else raw.decode()
    try:
        return tablib.Databook().load(data, format=fmt, **extra_load_args)
    except (tablib.UnsupportedFormat, KeyError, TypeError):
        return None


def try_load_file(
    file_name: Path,
    extra_args: dict[str, Any],
    in_format: str | None = None,
) -> tablib.Databook | tablib.Dataset:
    """Load a file, returning a Databook when possible, else a Dataset.

    Encapsulates the "try Databook, fall back to Dataset" handshake so
    callers don't reimplement it.
    """
    book = load_databook_file(file_name, extra_args=extra_args, in_format=in_format)
    if book is not None:
        return book
    return load_dataset_file(file_name, extra_args=extra_args, in_format=in_format)


def try_load_stdin(
    in_format: str | None = None,
    extra_args: dict[str, Any] | None = None,
    *,
    stdin: IO[bytes] | None = None,
) -> tablib.Databook | tablib.Dataset:
    """Load stdin, returning a Databook when possible, else a Dataset.

    Reads stdin once and tries both interpretations on the same bytes,
    so callers don't need to choose load_databook_stdin vs
    load_dataset_stdin up front (stdin can only be consumed once).
    """
    raw, fmt, extra_load_args = _read_and_detect_stdin(in_format, extra_args, stdin)
    data = raw if is_bin(fmt) else raw.decode()
    try:
        return tablib.Databook().load(data, format=fmt, **extra_load_args)
    except (tablib.UnsupportedFormat, KeyError, TypeError):
        return tablib.import_set(data, format=fmt, **extra_load_args)


def _read_and_detect_stdin(
    in_format: str | None,
    extra_args: dict[str, Any] | None,
    stdin: IO[bytes] | None = None,
) -> tuple[bytes, str, dict[str, Any]]:
    """Read stdin once, detect its format, and filter load kwargs.

    Returns (raw_bytes, format, filtered_load_kwargs). stdin substitutes
    any binary stream for the real sys.stdin.buffer (resolved at call
    time, so tests can inject a BytesIO without patching global state).
    """
    if extra_args is None:
        extra_args = {}
    raw = (sys.stdin.buffer if stdin is None else stdin).read()
    if not raw:
        msg = "No data received on stdin"
        raise TublubError(msg)

    fmt = in_format or _detect_format_from_bytes(raw)
    if fmt is None:
        msg = "Unable to detect input format from stdin; use -f to specify it"
        raise TublubError(msg)

    return raw, fmt, filter_args("load", extra_args, fmt)


def save_dataset_file(
    data: tablib.Dataset,
    file_name: Path,
    extra_args: dict[str, Any],
    force_format: str | None = None,
) -> None:
    """Save a Tablib dataset to a file."""
    file_format = _resolve_output_format(force_format, file_name)

    cfg = FORMATS.get(file_format, _DEFAULT_FMT)
    with _open_for_format(file_name, cfg, write=True) as fh:
        export_dataset(data, file_format, extra_args, file_handle=fh)

    print(f"Saved '{file_name}', {len(data)} records ({file_format})")


def build_databook(
    paths: list[Path],
    extra_args: dict[str, Any],
    in_format: str | None = None,
) -> tablib.Databook:
    """Build a Databook from multiple input files, expanding every sheet.

    An input with sheet structure contributes all its sheets under their
    own titles; any other input contributes one sheet titled by its file
    stem. Titles are kept verbatim; only clashing titles fall back to a
    qualified form — a sheet by its workbook's stem (book__Users), a stem
    by its parent directory (data_a) — see _unique_titles.
    """
    sheets: list[tablib.Dataset] = []
    entries: list[tuple[str, str]] = []
    for path in paths:
        loaded = try_load_file(path, extra_args=extra_args, in_format=in_format)
        if isinstance(loaded, tablib.Databook):
            for sheet in loaded.sheets():
                title = sheet.title or ""
                sheets.append(sheet)
                entries.append((title, f"{path.stem}__{title}"))
        else:
            qualified = path.stem
            if path.parent.name:
                qualified = f"{path.parent.name}_{path.stem}"
            sheets.append(loaded)
            entries.append((path.stem, qualified))
    book = tablib.Databook()
    for sheet, title in zip(sheets, _unique_titles(entries), strict=True):
        sheet.title = title
        book.add_sheet(sheet)
    return book


def save_databook_file(
    book: tablib.Databook,
    file_name: Path,
    extra_args: dict[str, Any],
    force_format: str | None = None,
    *,
    hint: str | None = None,
) -> None:
    """Save a Tablib Databook (multi-sheet workbook) to a file.

    hint, when given, is appended to the unsupported-format error message
    (the advice differs per caller: sheet selection can suggest --sheet,
    the multi-input path must not). A target that cannot hold the sheets
    raises MultiSheetUnsupportedError.
    """
    file_format = _resolve_output_format(force_format, file_name)

    cfg = FORMATS.get(file_format, _DEFAULT_FMT)
    with _open_for_format(file_name, cfg, write=True) as fh:
        export_databook(book, file_format, extra_args, file_handle=fh, hint=hint)

    print(f"Saved '{file_name}', {book.size} sheets ({file_format})")


def export_databook(
    book: tablib.Databook,
    target_format: str,
    extra_args: dict[str, Any],
    file_handle: IO[str] | IO[bytes] | None = None,
    *,
    hint: str | None = None,
) -> None:
    """Export a Databook to a file handle or other stream.

    Mirrors export_dataset, including its stdout newline handling.
    Multi-sheet capability is discovered by attempting the export, never
    from a static table; hint is appended to the unsupported-format error
    message when given. That failure raises MultiSheetUnsupportedError, so
    callers can tell it apart from every other TublubError.
    """
    to_stdout = file_handle is None
    if file_handle is None:
        file_handle = _default_export_handle(target_format)
    extra_save_args = filter_args("save", extra_args, target_format)
    try:
        output = book.export(target_format, **extra_save_args)
    except tablib.UnsupportedFormat as exc:
        msg = f"Format {target_format!r} does not support multi-sheet output"
        if hint:
            msg += f"; {hint}"
        raise MultiSheetUnsupportedError(msg, target_format) from exc
    if to_stdout and isinstance(output, str) and output and output[-1] != "\n":
        output += "\n"
    file_handle.write(output)


def _fit_title(base: str, suffix: str = "") -> str:
    """Fit a title base plus an optional suffix within XLSX_TITLE_LIMIT."""
    return base[: XLSX_TITLE_LIMIT - len(suffix)] + suffix


def _unique_titles(entries: list[tuple[str, str]]) -> list[str]:
    """Resolve (preferred, qualified) title pairs into unique sheet titles.

    A preferred title that occurs once is kept verbatim; one that clashes
    with another entry's preferred title falls back to its qualified form,
    which the caller derives from the sheet's container (a workbook stem
    for a sheet, a parent directory for a file stem). Underscore joins are
    used because XLSX sheet titles forbid the characters slash, backslash,
    question mark, asterisk, and brackets. Titles are clamped to
    XLSX_TITLE_LIMIT (XLSX caps worksheet titles at 31 characters). If the
    qualified or clamped title also collides (two sheets of the same name
    in one workbook, a path with no parent name, or two long titles
    sharing a 31-char prefix), a _2/_3 numeric suffix kicks in on top,
    with the base trimmed so the suffix still fits. A stderr note is
    emitted whenever any title had to change so users notice that the
    workbook's sheet names don't match the inputs verbatim.
    """
    preferred_counts = Counter(preferred for preferred, _ in entries)
    titles: list[str] = []
    used: set[str] = set()
    for preferred, qualified in entries:
        base = _fit_title(qualified if preferred_counts[preferred] > 1 else preferred)
        candidate = base
        n = 1
        while candidate in used:
            n += 1
            candidate = _fit_title(base, f"_{n}")
        used.add(candidate)
        titles.append(candidate)
    if any(t != preferred for t, (preferred, _) in zip(titles, entries, strict=True)):
        print(
            "Note: sheet titles disambiguated (name collisions or 31-char limit)",
            file=sys.stderr,
        )
    return titles


def export_dataset(
    data: tablib.Dataset,
    target_format: str,
    extra_args: dict[str, Any],
    file_handle: IO[str] | IO[bytes] | None = None,
) -> None:
    """Export dataset to a file handle or other stream.

    With no file_handle the export goes to stdout, where text output is
    newline-terminated so the shell prompt starts on its own line. Handles
    passed by the caller (the -o file paths) are written verbatim.
    """
    to_stdout = file_handle is None
    if file_handle is None:
        file_handle = _default_export_handle(target_format)
    extra_save_args = filter_args("save", extra_args, target_format)
    output = data.export(target_format, **extra_save_args)
    if to_stdout and isinstance(output, str) and output and output[-1] != "\n":
        output += "\n"
    file_handle.write(output)


def _default_export_handle(
    target_format: str, stdout: TextIO | None = None
) -> IO[str] | IO[bytes]:
    """Pick a stdout stream for the format, or raise for binary-to-TTY.

    stdout substitutes any text stream (with a .buffer) for the real
    sys.stdout, resolved at call time so tests can inject one without
    patching global state.
    """
    if stdout is None:
        stdout = sys.stdout
    if is_bin(target_format):
        if stdout.isatty():
            msg = f"Format {target_format} is binary, not printing to console!"
            raise TublubError(msg)
        return stdout.buffer
    return stdout


def filter_args(
    phase: str,
    user_args: dict[str, Any],
    file_format: str | None,
) -> dict[str, Any]:
    """Select keyword arguments allowed for the given format and phase.

    Phase is "load" or "save".
    """
    if file_format is None:
        return {}
    cfg = FORMATS.get(file_format, _DEFAULT_FMT)
    allowed = cfg.load_args if phase == "load" else cfg.save_args
    return {k: v for k, v in user_args.items() if k in allowed and v is not None}


@functools.cache
def get_formats() -> tuple[str, ...]:
    """Get a list of all available Tablib formats."""
    return tuple(x.title for x in tablib.formats.registry.formats())


def _looks_like_text_lines(text: str) -> bool:
    """Return True if text looks like lines of plain-text tabular data.

    Last-resort heuristic for when tablib's detect_format() fails, e.g.
    single-column CSV/TSV where csv.Sniffer can't find a delimiter.
    Requiring no commas or tabs ensures we only match genuinely single-column
    data, and avoids misdetecting prose (emails, READMEs, Markdown) which
    almost always contains commas.
    """
    stripped = text.strip()
    has_lines = "\n" in stripped
    has_delimiters = any(c in stripped for c in ",\t;|")
    return bool(stripped and has_lines and not has_delimiters)


def is_bin(data_format: str | None) -> bool:
    """Return true if data format is binary."""
    return FORMATS.get(data_format or "", _DEFAULT_FMT).binary


def parse_command_line(
    argv: list[str] | None = None,
    *,
    stdin_isatty: bool | None = None,
) -> tuple[argparse.Namespace, dict[str, Any]]:
    """Parse and return input arguments.

    stdin_isatty overrides the sys.stdin.isatty() probe used for implicit
    stdin inference, so tests can exercise both cases without patching
    global state (None means: ask the real stdin).
    """
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    infiles, outfile = _reconcile_positionals(parser, args)

    # Stdin handling — only meaningful for single-input mode
    args.stdin = False
    if len(infiles) >= _MIN_DATABOOK_INPUTS and _DASH in infiles:
        parser.error("Cannot use stdin '-' with multiple input files")
    if infiles == [_DASH]:
        infiles = []
        args.stdin = True
    elif _should_use_implicit_stdin(infiles, args, stdin_isatty=stdin_isatty):
        args.stdin = True

    args.outfile = outfile
    args.infiles = infiles

    _validate_args(parser, args)
    args.sheets = _cook_sheet_tokens(parser, args.sheets)

    return args, _collect_extra_args(args)


def _cook_sheet_tokens(
    parser: argparse.ArgumentParser, occurrences: list[str] | None
) -> list[str] | None:
    """Expand --sheet occurrences into selector tokens.

    An occurrence is comma-split only when every comma-piece is an integer
    (after strip); otherwise it is one literal title token, kept whole so
    titles like "Revenue, EMEA" survive.
    """
    if occurrences is None:
        return None
    tokens: list[str] = []
    for occ in occurrences:
        tokens.extend(_cook_one_occurrence(parser, occ))
    return tokens


def _cook_one_occurrence(parser: argparse.ArgumentParser, occ: str) -> list[str]:
    """Split one --sheet occurrence into tokens (see _cook_sheet_tokens)."""
    pieces = [p.strip() for p in occ.split(",")]
    if not all(pieces):
        parser.error("no sheet selector given")
    if all(_is_int_token(p) for p in pieces):
        return pieces
    return [occ]


def _is_int_token(token: str) -> bool:
    """Return True if the token parses as an integer."""
    try:
        int(token)
    except ValueError:
        return False
    return True


def _should_use_implicit_stdin(
    infiles: list[Path],
    args: argparse.Namespace,
    *,
    stdin_isatty: bool | None = None,
) -> bool:
    """Whether to read stdin even though no '-' was given on the command line.

    True when nothing was passed on the command line and stdin is a pipe
    (not a TTY), so `cmd | tublub` works without an explicit '-'. An
    interactive TTY with no input is a usage error, not stdin, so we
    return False there and let validation report "No input data provided."

    The real sys.stdin.isatty() is probed only when stdin_isatty is None,
    and only after the cheap checks, so file-input invocations (and tests
    passing an explicit value) never touch the real stdin.
    """
    if infiles or args.list_formats:
        return False
    if stdin_isatty is None:
        stdin_isatty = sys.stdin.isatty()
    return not stdin_isatty


def _collect_extra_args(args: argparse.Namespace) -> dict[str, Any]:
    """Gather format-specific kwargs (delimiter, skip_lines, ...) set on args."""
    known: set[str] = set()
    for cfg in FORMATS.values():
        known |= cfg.load_args | cfg.save_args
    return {
        key: value for key in known if (value := getattr(args, key, None)) is not None
    }


def _reconcile_positionals(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> tuple[list[Path], Path | None]:
    """Map positional inputs + -o into (infiles, outfile).

    Two invocation styles:
      New: -o OUT INFILE [INFILE ...]   (multi-input → Databook when 2+)
      Old: INFILE [OUTFILE]             (max two positionals)
    """
    raw_inputs: list[Path] = list(args.inputs or [])
    explicit_output: Path | None = args.output

    if explicit_output is not None:
        return list(raw_inputs), explicit_output

    if len(raw_inputs) > _MIN_DATABOOK_INPUTS:
        parser.error(
            "Too many positional arguments; "
            "use -o/--output to combine multiple input files"
        )
    infiles: list[Path] = [raw_inputs[0]] if raw_inputs else []
    outfile = raw_inputs[1] if len(raw_inputs) >= _MIN_DATABOOK_INPUTS else None
    return infiles, outfile


def _validate_list_sheets(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    """Reject flag combinations and input shapes incompatible with --list-sheets."""
    if args.list_formats:
        parser.error("Can not combine --list-sheets with --list-formats")
    if args.outfile:
        parser.error("Can not combine --list-sheets with -o/--output")
    if args.out_format:
        parser.error("Can not combine --list-sheets with -t/--to")
    if not args.infiles and not args.stdin:
        parser.error("--list-sheets requires an input file")
    if len(args.infiles) > 1:
        parser.error("--list-sheets accepts only one input file")


def _validate_sheet(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Reject flag combos and input shapes incompatible with --sheet/--all-sheets."""
    if args.sheets is not None and args.all_sheets:
        parser.error("Can not combine --sheet with --all-sheets")
    flag = "--sheet" if args.sheets is not None else "--all-sheets"
    if args.list_formats:
        parser.error(f"Can not combine {flag} with --list-formats")
    if args.list_sheets:
        parser.error(f"Can not combine {flag} with --list-sheets")
    if not args.infiles and not args.stdin:
        parser.error(f"{flag} requires an input file")
    if len(args.infiles) > 1:
        parser.error(f"{flag} is not supported with multiple inputs")


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Validate parsed args; calls parser.error (which exits) on problems."""
    if args.list_formats and (args.infiles or args.outfile):
        parser.error("Can not combine --list-formats with filename(s)")

    if args.list_sheets:
        _validate_list_sheets(parser, args)

    if args.sheets is not None or args.all_sheets:
        _validate_sheet(parser, args)

    if not args.list_formats and not args.infiles and not args.stdin:
        parser.error("No input data provided.")

    for f in args.infiles:
        if not f.is_file():
            parser.error(f"Input file {f} does not exist.")

    _check_known_format(parser, args.out_format, "format")
    _check_known_format(parser, args.in_format, "input format")


def _check_known_format(
    parser: argparse.ArgumentParser, fmt: str | None, label: str
) -> None:
    """parser.error (which exits) if fmt is set but not a known tablib format."""
    if fmt and fmt not in get_formats():
        parser.error(f"Invalid {label} {fmt}, use one of: {get_formats()}")


def build_argument_parser() -> argparse.ArgumentParser:
    """Parse and return command line arguments."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"available formats: {' '.join(get_formats())}",
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--list-formats",
        dest="list_formats",
        action="store_true",
        help="list the available file formats and exit",
    )
    parser.add_argument(
        "--dialect",
        metavar="DIALECT",
        choices=csv.list_dialects(),
        help="for CSV, input/output dialect {excel, unix}",
    )
    parser.add_argument(
        "-d", "--delimiter", metavar="C", help="for CSV, input/output delimiter"
    )
    parser.add_argument(
        "-q", "--quotechar", metavar="C", help="for CSV, input/output quote char"
    )

    input_group = parser.add_argument_group(title="input options")
    input_group.add_argument(
        "-H",
        "--no-headers",
        dest="headers",
        action="store_const",
        const=False,
        default=None,
        help="CSV/TSV input data has no header row",
    )
    input_group.add_argument(
        "--skip-lines",
        type=int,
        metavar="LINES",
        help="for CSV/TSV/XLS/XLSX input, skip lines at the top",
    )
    input_group.add_argument(
        "--no-xlsx-optimize",
        dest="read_only",
        action="store_const",
        const=False,
        default=None,
        help="disable optimized ('read_only') loading of XLSX files",
    )
    input_group.add_argument(
        "-f",
        "--from",
        metavar="FMT",
        dest="in_format",
        help="override input format (e.g. for .txt files or undetectable content)",
    )
    input_group.add_argument(
        "-l",
        "--list-sheets",
        dest="list_sheets",
        action="store_true",
        help=(
            'list sheets in the input and exit: "[idx] title  rows x cols" '
            'per sheet, or one bare "rows x cols" line if the input has no sheets'
        ),
    )
    input_group.add_argument(
        "-s",
        "--sheet",
        dest="sheets",
        metavar="SEL",
        action="append",
        help=(
            "select sheet(s) by 0-based index or title: '-s 0,2' picks "
            "indices, repeat -s to pick several titles, 'name:2024' forces "
            "a title match"
        ),
    )
    input_group.add_argument(
        "--all-sheets",
        dest="all_sheets",
        action="store_true",
        help=(
            "select every sheet of a multi-sheet input; on an input without "
            "sheet structure this changes nothing"
        ),
    )

    output_group = parser.add_argument_group(title="output options")
    output_group.add_argument(
        "-t",
        "--to",
        metavar="FMT",
        dest="out_format",
        help="output format (default: outfile extension, or none)",
    )
    output_group.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        type=Path,
        help=(
            "output file; with multiple inputs, combine them into one "
            "multi-sheet file (e.g. XLSX, ODS, JSON)"
        ),
    )
    output_group.add_argument(
        "--tablefmt",
        help="CLI output; Tabulate table format, e.g. 'fancy_grid'",
    )

    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        metavar="FILE",
        help=(
            "input file(s), or '-' for stdin. "
            "Without -o: [INFILE [OUTFILE]]; with -o: one or more input files"
        ),
    )

    return parser


if __name__ == "__main__":
    sys.exit(cli())

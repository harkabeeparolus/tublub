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
from typing import IO, Any

import tablib
import tablib.formats

from tublub import __version__


class TublubError(ValueError):
    """Raised for tublub-specific errors (bad format, empty data, etc.)."""


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


def cli() -> int:
    """Run the command line interface."""
    args, extra_args = parse_command_line()

    if args.list_formats:
        print("Available formats:", " ".join(get_formats()))
        return 0
    if args.list_sheets:
        return _run_list_sheets(args, extra_args)
    if len(args.infiles) >= _MIN_DATABOOK_INPUTS:
        return _run_databook(args, extra_args)
    return _run_single(args, extra_args)


def _run_single(args: argparse.Namespace, extra_args: dict[str, Any]) -> int:
    """Load one input (file or stdin) as a Dataset and render it."""
    try:
        if args.stdin:
            my_data = load_dataset_stdin(
                in_format=args.in_format, extra_args=extra_args
            )
        else:
            my_data = load_dataset_file(
                args.infiles[0], extra_args=extra_args, in_format=args.in_format
            )
    except TublubError as exc:
        sys.exit(str(exc))
    if not my_data:
        source = "stdin" if args.stdin else str(args.infiles[0])
        sys.exit(f"No data was loaded from {source}")

    try:
        if args.outfile:
            save_dataset_file(
                my_data,
                file_name=args.outfile,
                force_format=args.out_format,
                extra_args=extra_args,
            )
        elif args.out_format:
            export_dataset(my_data, args.out_format, extra_args=extra_args)
        else:
            print(my_data)
    except TublubError as exc:
        sys.exit(str(exc))

    return 0


def _run_list_sheets(args: argparse.Namespace, extra_args: dict[str, Any]) -> int:
    """Print one line per sheet in the input file (title, rows, cols)."""
    path: Path = args.infiles[0]
    try:
        loaded = try_load_file(path, extra_args=extra_args, in_format=args.in_format)
    except TublubError as exc:
        sys.exit(str(exc))
    if isinstance(loaded, tablib.Databook):
        for idx, sheet in enumerate(loaded.sheets()):
            ncols = len(sheet.headers or [])
            print(f"[{idx}] {sheet.title}  {len(sheet)} rows x {ncols} cols")
    else:
        ncols = len(loaded.headers or [])
        print(f"[0] {path.stem}  {len(loaded)} rows x {ncols} cols")
    return 0


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
    in_format: str | None = None, extra_args: dict[str, Any] | None = None
) -> tablib.Dataset:
    """Load a dataset from stdin."""
    raw, fmt, extra_load_args = _read_and_detect_stdin(in_format, extra_args)
    data = raw if is_bin(fmt) else raw.decode()
    return tablib.import_set(data, format=fmt, **extra_load_args)


def load_databook_stdin(
    in_format: str | None = None, extra_args: dict[str, Any] | None = None
) -> tablib.Databook | None:
    """Try to load a multi-sheet Tablib Databook from stdin.

    Returns None when the input is not a Databook (caller should fall
    back to load_dataset_stdin). Mirrors load_databook_file on the file
    side; see that docstring for the catch policy. Note: stdin can only
    be consumed once, so callers must choose this helper or
    load_dataset_stdin per invocation, not both.
    """
    raw, fmt, extra_load_args = _read_and_detect_stdin(in_format, extra_args)
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
) -> tablib.Databook | tablib.Dataset:
    """Load stdin, returning a Databook when possible, else a Dataset.

    Reads stdin once and tries both interpretations on the same bytes,
    so callers don't need to choose load_databook_stdin vs
    load_dataset_stdin up front (stdin can only be consumed once).
    """
    raw, fmt, extra_load_args = _read_and_detect_stdin(in_format, extra_args)
    data = raw if is_bin(fmt) else raw.decode()
    try:
        return tablib.Databook().load(data, format=fmt, **extra_load_args)
    except (tablib.UnsupportedFormat, KeyError, TypeError):
        return tablib.import_set(data, format=fmt, **extra_load_args)


def _read_and_detect_stdin(
    in_format: str | None,
    extra_args: dict[str, Any] | None,
) -> tuple[bytes, str, dict[str, Any]]:
    """Read stdin once, detect its format, and filter load kwargs.

    Returns (raw_bytes, format, filtered_load_kwargs).
    """
    if extra_args is None:
        extra_args = {}
    raw = sys.stdin.buffer.read()
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
    """Build a Databook from multiple input files, one sheet per file."""
    titles = _unique_titles(paths)
    book = tablib.Databook()
    for path, title in zip(paths, titles, strict=True):
        ds = load_dataset_file(path, extra_args=extra_args, in_format=in_format)
        ds.title = title
        book.add_sheet(ds)
    return book


def save_databook_file(
    book: tablib.Databook,
    file_name: Path,
    extra_args: dict[str, Any],
    force_format: str | None = None,
) -> None:
    """Save a Tablib Databook (multi-sheet workbook) to a file."""
    file_format = _resolve_output_format(force_format, file_name)

    cfg = FORMATS.get(file_format, _DEFAULT_FMT)
    extra_save_args = filter_args("save", extra_args, file_format)

    try:
        output = book.export(file_format, **extra_save_args)
    except tablib.UnsupportedFormat as exc:
        msg = f"Format {file_format!r} does not support multi-sheet output"
        raise TublubError(msg) from exc

    with _open_for_format(file_name, cfg, write=True) as fh:
        fh.write(output)

    print(f"Saved '{file_name}', {book.size} sheets ({file_format})")


def _fit_title(base: str, suffix: str = "") -> str:
    """Fit a title base plus an optional suffix within XLSX_TITLE_LIMIT."""
    return base[: XLSX_TITLE_LIMIT - len(suffix)] + suffix


def _unique_titles(paths: list[Path]) -> list[str]:
    """Return sheet titles from path stems; disambiguate stem collisions.

    On stem collision (data/a.csv + backup/a.csv) the parent directory
    qualifies the title (data_a, backup_a). Underscore is used because
    XLSX sheet titles forbid the characters slash, backslash, question
    mark, asterisk, and brackets. Titles are clamped to XLSX_TITLE_LIMIT
    (XLSX caps worksheet titles at 31 characters). If the parent-qualified
    or clamped title also collides (same parent name twice in the input
    list, a path with no parent name, or two long stems sharing a 31-char
    prefix), a _2/_3 numeric suffix kicks in on top, with the base trimmed
    so the suffix still fits. A stderr note is emitted whenever any
    disambiguation happens so users notice that the workbook's sheet names
    don't match the input stems verbatim.
    """
    stem_counts = Counter(p.stem for p in paths)
    titles: list[str] = []
    used: set[str] = set()
    for path in paths:
        stem = path.stem
        if stem_counts[stem] > 1 and path.parent.name:
            base = _fit_title(f"{path.parent.name}_{stem}")
        else:
            base = _fit_title(stem)
        candidate = base
        n = 1
        while candidate in used:
            n += 1
            candidate = _fit_title(base, f"_{n}")
        used.add(candidate)
        titles.append(candidate)
    if any(t != p.stem for t, p in zip(titles, paths, strict=True)):
        print(
            "Note: sheet titles disambiguated (filename collisions or 31-char limit)",
            file=sys.stderr,
        )
    return titles


def export_dataset(
    data: tablib.Dataset,
    target_format: str,
    extra_args: dict[str, Any],
    file_handle: IO[str] | IO[bytes] | None = None,
) -> None:
    """Export dataset to a file handle or other stream."""
    if file_handle is None:
        file_handle = _default_export_handle(target_format)
    extra_save_args = filter_args("save", extra_args, target_format)
    output = data.export(target_format, **extra_save_args)
    file_handle.write(output)


def _default_export_handle(target_format: str) -> IO[str] | IO[bytes]:
    """Pick a stdout stream for the format, or raise for binary-to-TTY."""
    if is_bin(target_format):
        if sys.stdout.isatty():
            msg = f"Format {target_format} is binary, not printing to console!"
            raise TublubError(msg)
        return sys.stdout.buffer
    return sys.stdout


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
) -> tuple[argparse.Namespace, dict[str, Any]]:
    """Parse and return input arguments."""
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
    elif _should_use_implicit_stdin(infiles, args):
        args.stdin = True

    args.outfile = outfile
    args.infiles = infiles

    _validate_args(parser, args)

    return args, _collect_extra_args(args)


def _should_use_implicit_stdin(infiles: list[Path], args: argparse.Namespace) -> bool:
    """Whether to read stdin even though no '-' was given on the command line.

    True when nothing was passed on the command line and stdin is a pipe
    (not a TTY), so `cmd | tublub` works without an explicit '-'. An
    interactive TTY with no input is a usage error, not stdin, so we
    return False there and let validation report "No input data provided."
    """
    return not infiles and not args.list_formats and not sys.stdin.isatty()


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
    if args.stdin:
        parser.error("--list-sheets does not yet support stdin input")
    if not args.infiles:
        parser.error("--list-sheets requires an input file")
    if len(args.infiles) > 1:
        parser.error("--list-sheets accepts only one input file")


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Validate parsed args; calls parser.error (which exits) on problems."""
    if args.list_formats and (args.infiles or args.outfile):
        parser.error("Can not combine --list-formats with filename(s)")

    if args.list_sheets:
        _validate_list_sheets(parser, args)

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
        help="list sheets in the input file (title, rows, cols) and exit",
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

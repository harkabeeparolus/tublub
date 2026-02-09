"""Convert tabular information files between different formats using Tablib.

If no outfile is specified the result will be printed to STDOUT instead,
either in the requested output format, or pretty-printed as a table.
"""

# TODO: Multiple input files to single XLSX Databook output

import argparse
import csv
import functools
import sys
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

    if args.list:
        print("Available formats:", " ".join(get_formats()))
        return 0

    try:
        if args.stdin:
            my_data = load_dataset_stdin(
                in_format=args.in_format, extra_args=extra_args
            )
        else:
            my_data = load_dataset_file(
                args.infile, extra_args=extra_args, in_format=args.in_format
            )
    except TublubError as exc:
        sys.exit(str(exc))
    if not my_data:
        source = "stdin" if args.stdin else str(args.infile)
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


def guess_file_format(filename: Path | None = None) -> str | None:
    """Guess format from file name."""
    if filename and (suf := filename.suffix.lstrip(".")) and suf in get_formats():
        return suf
    return None


def load_dataset_file(
    file_name: Path,
    extra_args: dict[str, Any],
    in_format: str | None = None,
) -> tablib.Dataset:
    """Load a file into a Tablib dataset."""
    # Format resolution priority: explicit -f flag > content detection > extension.
    # We don't trust extensions alone because legacy web exports commonly use
    # wrong extensions (e.g. .xls for CSV data). We don't trust detection alone
    # because tablib's detect_format() relies on csv.Sniffer, which fails on
    # single-column CSV/TSV (no delimiter to sniff). The -f flag is the escape
    # hatch for when both fail (e.g. single-column CSV with a .txt extension).
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

    cfg = FORMATS.get(fmt, _DEFAULT_FMT)
    open_mode = "rb" if cfg.binary else "r"
    newline = cfg.open_kwargs.get("newline")
    extra_load_args = filter_args("load", extra_args, fmt)

    with file_name.open(open_mode, newline=newline) as fh:
        return tablib.import_set(fh, format=fmt, **extra_load_args)


def detect_format_from_file(file_name: Path) -> str | None:
    """Detect format from file content, independent of file extension.

    Tablib's detect_format() requires the file opened in the right mode:
    binary formats (xlsx, xls, ods, dbf) need "rb" or Python raises
    UnicodeDecodeError; CSV/TSV need "r" because csv.Sniffer requires str
    (returns None on bytes). JSON and YAML work in either mode.
    There is no single open mode that works for all formats, so we try
    binary first (catches binary formats + json + yaml) then text (csv/tsv).

    As a last resort, if the file looks like plain text lines, assume TSV.
    This catches single-column data where csv.Sniffer fails (no delimiter).
    TSV is preferred over CSV because it won't split on commas in values.
    """
    with file_name.open("rb") as fh:
        raw = fh.read()
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
    if extra_args is None:
        extra_args = {}
    raw = sys.stdin.buffer.read()
    if not raw:
        msg = "No data received on stdin"
        raise TublubError(msg)

    detect_format = in_format
    if detect_format is None:
        # Try binary first (detects xlsx, json, yaml, etc.)
        detect_format = tablib.detect_format(raw)
        if detect_format is None:
            # Fall back to text (detects csv, tsv), then text-lines heuristic
            try:
                text = raw.decode()
            except UnicodeDecodeError:
                text = None
            if text is not None:
                detect_format = tablib.detect_format(text)
                if detect_format is None and _looks_like_text_lines(text):
                    detect_format = "tsv"
    if detect_format is None:
        msg = "Unable to detect input format from stdin; use -f to specify it"
        raise TublubError(msg)

    extra_load_args = filter_args("load", extra_args, detect_format)

    # Provide data in the right type: str for text formats, bytes for binary
    if is_bin(detect_format):
        data = raw
    else:
        data = raw.decode() if isinstance(raw, bytes) else raw

    return tablib.import_set(data, format=detect_format, **extra_load_args)


def save_dataset_file(
    data: tablib.Dataset,
    file_name: Path,
    extra_args: dict[str, Any],
    force_format: str | None = None,
) -> None:
    """Save a Tablib dataset to a file."""
    file_format = force_format or guess_file_format(file_name)
    if file_format is None:
        msg = f"Unable to detect target file format for: {file_name}"
        raise TublubError(msg)

    cfg = FORMATS.get(file_format, _DEFAULT_FMT)
    newline = cfg.open_kwargs.get("newline")
    with file_name.open("wb" if cfg.binary else "w", newline=newline) as fh:
        export_dataset(data, file_format, extra_args, file_handle=fh)

    print(f"Saved '{file_name}', {len(data)} records ({file_format})")


def export_dataset(
    data: tablib.Dataset,
    target_format: str,
    extra_args: dict[str, Any],
    file_handle: IO[str] | IO[bytes] | None = None,
) -> None:
    """Export dataset to a file handle or other stream."""
    if file_handle is None:
        if is_bin(target_format):
            if sys.stdout.isatty():
                msg = f"Format {target_format} is binary, not printing to console!"
                raise TublubError(msg)
            file_handle = sys.stdout.buffer
        else:
            file_handle = sys.stdout
    if file_handle is None:  # Catch type warning for Pylance
        msg = "No output stream available for export"
        raise TublubError(msg)
    extra_save_args = filter_args("save", extra_args, target_format)
    output = data.export(target_format, **extra_save_args)
    file_handle.write(output)


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

    # Detect stdin mode: explicit "-" or implicit piped stdin
    args.stdin = False
    if args.infile == Path("-"):
        args.infile = None
        args.stdin = True
    elif not args.infile and not args.list and not sys.stdin.isatty():
        args.stdin = True

    # Sanity checking

    if args.list and (args.infile or args.outfile):
        parser.error("Can not combine --list with filename(s)")

    if not args.list and not args.infile and not args.stdin:
        parser.error("No input data provided.")

    if args.infile and not args.infile.is_file():
        parser.error(f"Input file {args.infile} does not exist.")

    if args.out_format and args.out_format not in get_formats():
        parser.error(f"Invalid format {args.out_format}, use one of: {get_formats()}")

    if args.in_format and args.in_format not in get_formats():
        parser.error(
            f"Invalid input format {args.in_format}, use one of: {get_formats()}"
        )

    # Make a dict of all args.xxx for xxx in the FormatConfig structures
    all_extra_args: set[str] = set()
    for cfg in FORMATS.values():
        all_extra_args |= cfg.load_args | cfg.save_args
    extra_args = {
        key: value
        for key in all_extra_args
        if (value := getattr(args, key, None)) is not None
    }

    return args, extra_args


def build_argument_parser() -> argparse.ArgumentParser:
    """Parse and return command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "-l",
        "--list",
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
        "--in-format",
        metavar="FMT",
        dest="in_format",
        help="override input format (e.g. for .txt files or undetectable content)",
    )

    output_group = parser.add_argument_group(title="output options")
    output_group.add_argument(
        "-t",
        "--format",
        metavar="FMT",
        dest="out_format",
        help="output format (default: outfile extension, or none)",
    )
    output_group.add_argument(
        "--tablefmt",
        help="CLI output; Tabulate table format, e.g. 'fancy_grid'",
    )

    parser.add_argument(
        "infile", nargs="?", type=Path, help="input (source) file, or '-' for stdin"
    )
    parser.add_argument(
        "outfile", nargs="?", type=Path, help="output (destination) file"
    )

    return parser


if __name__ == "__main__":
    sys.exit(cli())

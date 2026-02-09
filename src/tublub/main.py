"""Convert tabular information files between different formats using Tablib.

If no outfile is specified the result will be printed to STDOUT instead,
either in the requested output format, or pretty-printed as a table.
"""

# TODO: Multiple input files to single XLSX Databook output

import argparse
import csv
import functools
import sys
from pathlib import Path
from typing import IO, Any

import tablib
import tablib.exceptions
import tablib.formats

from tublub import __version__


class TublubError(ValueError):
    """Raised for tublub-specific errors (bad format, empty data, etc.)."""


# https://tablib.readthedocs.io/en/stable/formats.html
BINARY_FORMATS = {"xlsx", "xls", "dbf", "ods"}
LOAD_EXTRA_ARGS = {
    "csv": {"skip_lines", "headers", "delimiter", "quotechar", "dialect"},
    "tsv": {"skip_lines", "headers"},
    "xls": {"skip_lines"},
    "xlsx": {"skip_lines", "read_only"},
}
SAVE_EXTRA_ARGS = {"cli": {"tablefmt"}, "csv": {"delimiter", "quotechar", "dialect"}}
OPEN_EXTRA_ARGS = {"csv": {"newline": ""}}


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
            my_data = load_dataset_file(args.infile, extra_args=extra_args)
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


def load_dataset_file(file_name: Path, extra_args: dict[str, Any]) -> tablib.Dataset:
    """Load a file into a Tablib dataset."""
    guess_format = guess_file_format(file_name)

    # We open the file twice: once to detect format, once to import. We can't
    # simply seek back because the open mode (binary/text) may change after
    # detection resolves the actual format.
    #
    # Tablib's detect_format requires the correct open mode per format:
    # binary formats (xlsx, xls, ods, dbf) need "rb", while csv/tsv need "r"
    # (csv.Sniffer requires str). JSON and YAML work in either mode.
    # When the extension gives us a hint we use it; otherwise we try "rb"
    # first (detects binary + json + yaml) then fall back to "r" (csv/tsv).
    detect_format = None
    if guess_format is not None:
        with file_name.open("rb" if is_bin(guess_format) else "r") as fh:
            detect_format = tablib.detect_format(fh)
    else:
        with file_name.open("rb") as fh:
            detect_format = tablib.detect_format(fh)
        if detect_format is None:
            with file_name.open("r") as fh:
                detect_format = tablib.detect_format(fh)
    if guess_format and guess_format != detect_format:
        print(
            f"Guessed mode {guess_format} differs from Tablib detected {detect_format}",
            file=sys.stderr,
        )
    if detect_format is None:
        detect_format = guess_format
    if detect_format is None:
        msg = f"Unable to detect format for: {file_name}"
        raise TublubError(msg)

    open_mode = "rb" if is_bin(detect_format) else "r"
    newline = OPEN_EXTRA_ARGS.get(detect_format, {}).get("newline")
    extra_load_args = filter_args(LOAD_EXTRA_ARGS, extra_args, detect_format)

    with file_name.open(open_mode, newline=newline) as fh:
        return tablib.import_set(fh, format=detect_format, **extra_load_args)


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
            # Fall back to text (detects csv, tsv)
            try:
                text = raw.decode()
            except UnicodeDecodeError:
                text = None
            if text is not None:
                detect_format = tablib.detect_format(text)
    if detect_format is None:
        msg = "Unable to detect input format from stdin; use -f to specify it"
        raise TublubError(msg)

    extra_load_args = filter_args(LOAD_EXTRA_ARGS, extra_args, detect_format)

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

    newline = OPEN_EXTRA_ARGS.get(file_format, {}).get("newline")
    with file_name.open("wb" if is_bin(file_format) else "w", newline=newline) as fh:
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
    extra_save_args = filter_args(SAVE_EXTRA_ARGS, extra_args, target_format)
    output = data.export(target_format, **extra_save_args)
    file_handle.write(output)


def filter_args(
    args_by_format: dict[str, set[str]],
    user_args: dict[str, Any],
    file_format: str | None,
) -> dict[str, Any]:
    """Create and select keyword arguments for Dataset().load().

    Filtered by input data format.
    """
    if file_format is None:
        return {}
    allowed = args_by_format.get(file_format, set())
    return {k: v for k, v in user_args.items() if k in allowed and v is not None}


@functools.cache
def get_formats() -> tuple[str, ...]:
    """Get a list of all available Tablib formats."""
    return tuple(x.title for x in tablib.formats.registry.formats())


def is_bin(data_format: str | None) -> bool:
    """Return true if data format is binary."""
    return bool(data_format and data_format in BINARY_FORMATS)


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

    # Make a dict of all args.xxx for xxx in the EXTRA_ARGS structures
    all_extra_args = set().union(*LOAD_EXTRA_ARGS.values(), *SAVE_EXTRA_ARGS.values())
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
        help="input format (required for stdin if auto-detection fails)",
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

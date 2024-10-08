"""Convert tabular information files between different formats using Tablib.

If no outfile is specified the result will be printed to STDOUT instead,
either in the requested output format, or pretty-printed as a table.
"""

# TODO: Handle pipelines.
# TODO: Multiple input files to single XLSX Databook output

import argparse
import csv
import functools
import sys
from collections import defaultdict
from operator import or_
from pathlib import Path

import tablib
import tablib.exceptions
import tablib.formats

from tublub import __version__

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


def cli():
    """Run the command line interface."""
    args, extra_args = parse_command_line()

    if args.list:
        print("Available formats:", " ".join(get_formats()))
        return

    my_data = load_dataset_file(args.infile, extra_args=extra_args)
    if not my_data:
        sys.exit(f"No data was loaded from {args.infile}, exiting...")

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


def guess_file_format(filename=None):
    """Guess format from file name."""
    if filename:
        if (suf := Path(filename).suffix.lstrip(".")) and suf in get_formats():
            return suf
    return None


def load_dataset_file(file_name, extra_args):
    """Load a file into a Tablib dataset."""
    guess_format = guess_file_format(file_name)

    detect_format = None
    with open(file_name, "rb" if is_bin(guess_format) else "r") as fh:
        detect_format = tablib.detect_format(fh)
    if guess_format and guess_format != detect_format:
        print(
            f"Guessed mode {guess_format} differs from Tablib detected {detect_format}",
            file=sys.stderr,
        )
    if detect_format is None:
        detect_format = guess_format

    open_mode = "rb" if is_bin(detect_format) else "r"
    open_extra = OPEN_EXTRA_ARGS.get(detect_format, {})
    extra_load_args = filter_args(LOAD_EXTRA_ARGS, extra_args, detect_format)

    with open(file_name, open_mode, **open_extra) as fh:
        imported_data = tablib.import_set(fh, format=detect_format, **extra_load_args)

    return imported_data


def save_dataset_file(data, file_name, extra_args, force_format=None):
    """Save a Tablib dataset to a file."""
    file_format = force_format or guess_file_format(file_name)
    if not file_format:
        sys.exit(f"Unable to detect target file format for: {file_name}")

    open_extra = OPEN_EXTRA_ARGS.get(file_format, {})
    with open(file_name, "wb" if is_bin(file_format) else "w", **open_extra) as fh:
        export_dataset(data, file_format, extra_args, file_handle=fh)

    print(f"Saved '{file_name}', {len(data)} records ({file_format})")


def export_dataset(data, target_format, extra_args, file_handle=sys.stdout):
    """Export dataset to a file handle or other stream."""
    extra_save_args = filter_args(SAVE_EXTRA_ARGS, extra_args, target_format)
    output = data.export(target_format, **extra_save_args)

    if file_handle is sys.stdout and sys.stdout.isatty():
        if is_bin(target_format):
            sys.exit(f"Format {target_format} is binary, not printing to console!")
        print(output)
        return
    file_handle.write(output)


def filter_args(args_by_format, user_args, file_format):
    """Create and select keyword arguments for Dataset().load(),
    filtered by input data format.
    """
    load_filter = defaultdict(set, args_by_format)
    return {
        k: v
        for k, v in user_args.items()
        if k in load_filter[file_format] and v is not None
    }


@functools.cache
def get_formats():
    """Get a list of all available Tablib formats."""
    return tuple(x.title for x in tablib.formats.registry.formats())


def is_bin(data_format):
    """Return true if data format is binary."""
    return bool(data_format and data_format in BINARY_FORMATS)


def parse_command_line():
    """Parse and return input arguments."""
    parser = build_argument_parser()
    args = parser.parse_args()

    # Sanity checking

    if args.list and (args.infile or args.outfile):
        parser.error("Can not combine --list with filename(s)")

    if not args.list and not args.infile:
        parser.error("No input data provided.")

    if args.infile and not Path(args.infile).is_file():
        parser.error(f"Input file {args.infile} does not exist.")

    if args.out_format and args.out_format not in get_formats():
        parser.error(f"Invalid format {args.out_format}, use one of: {get_formats()}")

    # Make a dict of all args.xxx for xxx in the EXTRA_ARGS structures
    all_extra_args = functools.reduce(
        or_, {**LOAD_EXTRA_ARGS, **SAVE_EXTRA_ARGS}.values()
    )
    extra_args = {
        key: value
        for key in all_extra_args
        if (value := getattr(args, key, None)) is not None
    }

    return args, extra_args


def build_argument_parser():
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
        action="store_false",
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
        action="store_false",
        help="disable optimized ('read_only') loading of XLSX files",
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

    parser.add_argument("infile", nargs="?", help="input (source) file")
    parser.add_argument("outfile", nargs="?", help="output (destination) file")

    return parser


if __name__ == "__main__":
    sys.exit(cli())
